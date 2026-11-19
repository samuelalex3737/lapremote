"""FastAPI application: the /ws endpoint, static hosting of the Remote app and /api/health."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from starlette.websockets import WebSocket, WebSocketDisconnect

from lapremote import __version__
from lapremote.banner import render_banner
from lapremote.config import Config, data_dir, load_config
from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.discovery import Advertiser
from lapremote.input.service import InputDevices, detect_input_devices, register_input
from lapremote.logging_setup import get_logger, log_event, setup_logging
from lapremote.media.base import MediaBackend
from lapremote.media.keys_fallback import MediaKeys
from lapremote.media.service import MediaService, create_media_backend
from lapremote.protocol import Ack
from lapremote.router import MSG_INVALID
from lapremote.security.pairing import CODE_TTL_SECONDS
from lapremote.security.ratelimit import Limits
from lapremote.system.context import read_foreground
from lapremote.system.dpi import enable_dpi_awareness
from lapremote.system.network import detect_lan_ip
from lapremote.system.platform_info import detect_display_server
from lapremote.system.volume import VolumeBackend, VolumeService, create_volume_backend

PORT_ENV = "LAPREMOTE_PORT"
INPUT_DRY_RUN_ENV = "LAPREMOTE_INPUT_DRY_RUN"
STATIC_DIR = Path(__file__).resolve().parent / "static"
AUTH_TIMEOUT_SECONDS = 5.0
CLOSE_AUTH_TIMEOUT = 4001
CLOSE_BAD_ORIGIN = 4003

log = get_logger("server")

NOT_BUILT_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>LapRemote</title>
<style>body{font-family:system-ui,sans-serif;background:#0b0b10;color:#f4f4f6;
display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;text-align:center}
code{background:#1c1c24;padding:4px 8px;border-radius:8px}</style></head><body><div>
<h1>LapRemote</h1><p>The phone app hasn't been built yet.</p>
<p>On the laptop, run <code>uv run --project agent python scripts/build_web.py</code>
then restart the agent.</p></div></body></html>"""


class HealthResponse(BaseModel):
    """Unauthenticated, so it must never reveal host, OS, device or session details."""

    ok: Literal[True]
    version: str
    uptime: float


def _normalise_netloc(scheme: str, netloc: str) -> str:
    netloc = netloc.lower()
    default = {"http": ":80", "https": ":443"}.get(scheme)
    if default and netloc.endswith(default):
        netloc = netloc[: -len(default)]
    return netloc


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """The page that opened the socket must be served from this same host and port."""
    if not origin or not host:
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    return _normalise_netloc(parts.scheme, parts.netloc) == _normalise_netloc(parts.scheme, host)


class SpaStaticFiles(StaticFiles):
    """Serves the built Remote app and falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api"):
                raise
            response = await super().get_response("index.html", scope)
        else:
            if response.status_code == 404 and not path.startswith("api"):
                response = await super().get_response("index.html", scope)
        path = path.replace("\\", "/")
        if path in ("", ".", "index.html") or response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _print(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


@dataclass(frozen=True)
class ServerOptions:
    port: int
    lan_ip: str | None
    advertise: bool
    print_banner: bool
    auth_timeout: float


def _make_lifespan(
    agent: Agent, opts: ServerOptions
) -> Callable[[FastAPI], contextlib.AbstractAsyncContextManager[None]]:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ip = opts.lan_ip if opts.lan_ip is not None else await asyncio.to_thread(detect_lan_ip)
        app.state.lan_ip = ip
        if opts.print_banner:
            https = agent.config.https.enabled
            minutes = int(CODE_TTL_SECONDS // 60)

            def show(code: str) -> None:
                _print(render_banner(ip, opts.port, code, minutes, https=https))

            agent.add_code_listener(show)
            show(agent.pairing.current()[0])

        async def watch_code() -> None:
            # Rotates the code (and reprints the banner) as soon as it expires.
            while True:
                await asyncio.sleep(1.0)
                agent.pairing.current()

        watcher = asyncio.create_task(watch_code())
        advertiser = Advertiser()
        if opts.advertise and ip is not None:
            await advertiser.start(ip, opts.port, agent.host_name)
        await agent.startup()
        log_event(log, "agent_started", version=__version__, port=opts.port, lanIp=ip)
        try:
            yield
        finally:
            await agent.shutdown()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            await advertiser.stop()
            for conn in agent.hub:
                await conn.close(1001, "agent stopping")
            log_event(log, "agent_stopped")

    return lifespan


async def _auth_deadline(conn: Connection, seconds: float) -> None:
    await asyncio.sleep(seconds)
    if not conn.authed:
        log_event(log, "auth_timeout", conn=conn.conn_id)
        await conn.close(CLOSE_AUTH_TIMEOUT, "auth timeout")


async def serve_socket(agent: Agent, ws: WebSocket, auth_timeout: float) -> None:
    """One phone connection, from the Origin check to disconnect."""
    if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
        log_event(log, "origin_rejected", origin=ws.headers.get("origin"))
        await ws.close(code=CLOSE_BAD_ORIGIN)
        return
    await ws.accept()
    ip = ws.client.host if ws.client is not None else "unknown"
    conn = Connection(ws, ip, agent.limits, agent.clock)
    agent.hub.add(conn)
    log_event(log, "connected", conn=conn.conn_id, ip=ip)
    deadline = asyncio.create_task(_auth_deadline(conn, auth_timeout))
    try:
        while not conn.closed:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            text = message.get("text")
            if text is not None:
                await agent.router.handle_text(conn, text)
            else:
                # Phones never send binary frames.
                await conn.send("ack", Ack(id="", ok=False, error=MSG_INVALID))
    except (WebSocketDisconnect, RuntimeError) as exc:
        log_event(log, "socket_ended", level=10, conn=conn.conn_id, reason=type(exc).__name__)
    finally:
        deadline.cancel()
        conn.closed = True
        await agent.disconnected(conn)
        log_event(log, "disconnected", conn=conn.conn_id, device=conn.device_id)


def create_app(  # noqa: PLR0913 - explicit knobs keep tests free of monkeypatching
    config: Config | None = None,
    *,
    home: Path | None = None,
    static_dir: Path | None = None,
    port: int | None = None,
    lan_ip: str | None = None,
    advertise: bool = True,
    print_banner: bool = True,
    console_log: bool = True,
    limits: Limits | None = None,
    auth_timeout: float = AUTH_TIMEOUT_SECONDS,
    input_devices: InputDevices | None = None,
    media_backend: MediaBackend | None = None,
    volume_backend: VolumeBackend | None = None,
) -> FastAPI:
    # Before anything touches the screen, so coordinates are physical pixels on Windows.
    dpi_mode = enable_dpi_awareness()
    home = home or data_dir()
    config = config or load_config()
    setup_logging(home / "logs", console=console_log)
    agent = Agent(config, home, limits=limits)
    if input_devices is None:
        input_devices = detect_input_devices(
            agent.os,
            detect_display_server(agent.os),
            dry_run=os.environ.get(INPUT_DRY_RUN_ENV) == "1",
        )
    register_input(agent, input_devices)
    keys = MediaKeys(input_devices.keyboard)
    hint: str | None = None
    if media_backend is None:
        media_backend, hint = create_media_backend(agent.os)
    MediaService(agent, media_backend, keys, read_foreground, hint).register()
    VolumeService(agent, volume_backend or create_volume_backend(agent.os), keys).register()
    log_event(log, "input_ready", available=input_devices.permission.available, dpi=dpi_mode)
    opts = ServerOptions(
        port=port or int(os.environ.get(PORT_ENV) or config.port),
        lan_ip=lan_ip,
        advertise=advertise,
        print_banner=print_banner,
        auth_timeout=auth_timeout,
    )
    started = time.monotonic()
    app = FastAPI(
        title="LapRemote agent",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_make_lifespan(agent, opts),
    )
    app.state.agent = agent

    @app.get("/api/health")
    async def health() -> HealthResponse:
        return HealthResponse(
            ok=True, version=__version__, uptime=round(time.monotonic() - started, 1)
        )

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await serve_socket(agent, ws, opts.auth_timeout)

    static_root = static_dir or STATIC_DIR
    if (static_root / "index.html").is_file():
        app.mount("/", SpaStaticFiles(directory=static_root, html=True), name="remote")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def not_built() -> str:
            return NOT_BUILT_PAGE

    return app
