"""Fetch a website's own icon for a shortcut, safely.

The laptop fetches a URL the owner saved, so it is careful not to become a way into the local
network: every host (including each redirect) must resolve only to public internet addresses,
responses are size-capped and time-limited, and the image is decoded and re-encoded as a fresh
96x96 PNG, so nothing from the site is ever stored or served as-is.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from lapremote.apps import png_data_url
from lapremote.logging_setup import get_logger, log_event

log = get_logger("site_icons")

TIMEOUT = httpx.Timeout(4.0, connect=3.0)
MAX_PAGE_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 512 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "LapRemote icon fetcher"
MIN_ICON_PX = 8
MAX_ICON_PX = 1024
ICON_RELS = frozenset({"icon", "apple-touch-icon", "apple-touch-icon-precomposed"})
LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
ATTR = re.compile(r"""([a-zA-Z-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""")

Resolver = Callable[[str], Awaitable[list[str]]]


class BlockedHostError(Exception):
    """The host is not a public internet address."""


async def resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


async def check_public(url: str, resolver: Resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        msg = "only http(s) URLs with a host"
        raise BlockedHostError(msg)
    try:
        addresses = await resolver(parts.hostname)
    except OSError as exc:
        raise BlockedHostError(str(exc)) from exc
    if not addresses:
        msg = "host did not resolve"
        raise BlockedHostError(msg)
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            msg = f"{parts.hostname} is not on the public internet"
            raise BlockedHostError(msg)


async def _get(
    client: httpx.AsyncClient,
    url: str,
    limit: int,
    resolver: Resolver,
    *,
    truncate: bool = False,
) -> tuple[str, bytes, str]:
    """GET with manual, re-checked redirects and a byte cap. Returns (final url, body, type)."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await check_public(current, resolver)
        async with client.stream(
            "GET", current, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as response:
            if response.is_redirect and "location" in response.headers:
                current = urljoin(current, response.headers["location"])
                continue
            if response.status_code != 200:
                msg = f"HTTP {response.status_code}"
                raise httpx.HTTPError(msg)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > limit:
                    if truncate:
                        # A page declares its icons near the top: the start is enough.
                        del body[limit:]
                        break
                    msg = "response too large"
                    raise httpx.HTTPError(msg)
            return current, bytes(body), response.headers.get("content-type", "")
    msg = "too many redirects"
    raise httpx.HTTPError(msg)


def icon_links(page_url: str, html: str) -> list[str]:
    """Icon URLs from <link> tags, best first: apple-touch-icon, then the largest icon."""
    found: list[tuple[int, str]] = []
    for tag in LINK_TAG.findall(html[:MAX_PAGE_BYTES]):
        attrs = {m[0].lower(): unescape(m[2] or m[3] or m[4]) for m in ATTR.findall(tag)}
        rel = attrs.get("rel", "").lower().split()
        href = attrs.get("href")
        if not href or not (
            {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"} & set(rel)
        ):
            continue
        if href.lower().endswith(".svg") or "svg" in attrs.get("type", ""):
            continue  # can't be decoded safely without a full SVG renderer
        size = 0
        sizes = attrs.get("sizes", "")
        match = re.search(r"(\d+)x\d+", sizes)
        if match:
            size = int(match.group(1))
        if "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
            size = max(size, 180)
        found.append((size, urljoin(page_url, href)))
    found.sort(key=lambda item: -item[0])
    links = [url for _, url in found]
    links.append(urljoin(page_url, "/favicon.ico"))
    return list(dict.fromkeys(links))


def decode_icon(data: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            image: Image.Image = opened
            if opened.format == "ICO":
                # Use the largest image inside the .ico file.
                sizes = sorted(opened.info.get("sizes", {opened.size}), key=lambda s: s[0] * s[1])
                image = opened.ico.getimage(sizes[-1])  # type: ignore[attr-defined]
            # Check the size before decoding any pixels.
            if not (MIN_ICON_PX <= image.width <= MAX_ICON_PX):
                return None
            if not (MIN_ICON_PX <= image.height <= MAX_ICON_PX):
                return None
            image.load()
            return png_data_url(image)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def fetch_site_icon(
    url: str, client: httpx.AsyncClient, resolver: Resolver = resolve_host
) -> str | None:
    """The site's icon as a 96x96 PNG data URL, or None. Never raises."""
    try:
        await check_public(url, resolver)
        try:
            page_url, body, content_type = await _get(
                client, url, MAX_PAGE_BYTES, resolver, truncate=True
            )
            html = body.decode("utf-8", errors="replace") if "html" in content_type else ""
        except httpx.HTTPError:
            # Some sites refuse automated page loads: the site's /favicon.ico may still work.
            page_url, html = url, ""
        for icon_url in icon_links(page_url, html)[:5]:
            try:
                _, data, _ = await _get(client, icon_url, MAX_IMAGE_BYTES, resolver)
            except (httpx.HTTPError, BlockedHostError):
                continue
            icon = decode_icon(data)
            if icon is not None:
                return icon
    except (httpx.HTTPError, BlockedHostError) as exc:
        log_event(
            log, "site_icon_failed", level=20, host=urlsplit(url).hostname, error=str(exc)[:120]
        )
    return None
