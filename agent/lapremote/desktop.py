"""The /desktop dashboard: a page for the person sitting at the laptop.

Only the laptop itself can open it:
- the request must come from a loopback address, and the Host header must name localhost,
  so another machine on the Wi-Fi can't reach it and DNS rebinding can't either;
- every change needs a custom header and a localhost Origin, so a web page open in the
  laptop's browser can't trigger changes (a cross-site request can't set that header without
  a CORS preflight, which is never allowed);
- the page can't be framed, and its script runs under a nonce-based CSP.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import qrcode
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel
from qrcode.image.svg import SvgPathImage

from lapremote import __version__
from lapremote.autostart import Autostart
from lapremote.banner import pairing_url
from lapremote.config import CONFIG_FILENAME, Config, save_config
from lapremote.core import Agent
from lapremote.desktop_page import DASHBOARD_HTML
from lapremote.logging_setup import get_logger, log_event
from lapremote.netwatch import Move, NetworkWatch
from lapremote.protocol import Role
from lapremote.router import ActionError
from lapremote.services import Services

log = get_logger("desktop")

LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
WRITE_HEADER = "x-lapremote-desktop"

FEATURE_LABELS: dict[str, str] = {
    "input": "Mouse and keyboard control",
    "media": "Media controls",
    "volume": "Volume",
    "brightness": "Screen brightness",
    "preview": "Screen preview",
    "context": "Knowing which app is in front",
    "power": "Lock, sleep and shut down",
    "launcher": "Opening shortcuts",
    "ai": "AI assistant",
}
FIREWALL_HELP = (
    "If your phone can't connect, open Windows Security > Firewall & network protection > "
    "Allow an app through firewall, and allow Python (or LapRemote) on Private networks."
)
HTTPS_HELP = "Optional. Needed for voice input and the air mouse. See docs/HTTPS.md."
SETTINGS_RESTART = "Saved. Restart LapRemote to use the new settings."


def _hostname(host_header: str | None) -> str | None:
    if not host_header:
        return None
    return urlsplit(f"//{host_header}").hostname


def is_local(request: Request) -> bool:
    client = request.client.host if request.client is not None else None
    return client in LOOPBACK_CLIENTS and _hostname(request.headers.get("host")) in LOCAL_HOSTS


def _guard_read(request: Request) -> None:
    if not is_local(request):
        # 404, not 403: other machines don't learn that a dashboard exists.
        raise HTTPException(status_code=404)


def _guard_write(request: Request) -> None:
    _guard_read(request)
    origin = request.headers.get("origin")
    if request.headers.get(WRITE_HEADER) != "1":
        raise HTTPException(status_code=403)
    if origin is not None and _hostname(urlsplit(origin).netloc) not in LOCAL_HOSTS:
        raise HTTPException(status_code=403)


def qr_svg(data: str) -> str:
    image = qrcode.make(data, image_factory=SvgPathImage, border=2)
    svg: str = image.to_string(encoding="unicode")
    return svg


@dataclass
class DesktopContext:
    agent: Agent
    services: Services
    autostart: Autostart | None
    port: int


class PauseBody(BaseModel):
    paused: bool


class EnabledBody(BaseModel):
    enabled: bool


class RoleBody(BaseModel):
    role: Role


class SettingsBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    preferred_browser: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    preview_fps: int | None = None
    preview_width: int | None = None
    preview_quality: int | None = None


def _checklist(ctx: DesktopContext) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, label in FEATURE_LABELS.items():
        status = ctx.agent.feature_status[name]
        items.append(
            {"name": name, "label": label, "ok": status.available, "detail": status.reason}
        )
    items.append(
        {
            "name": "https",
            "label": "HTTPS",
            "ok": ctx.agent.config.https.enabled,
            "detail": None if ctx.agent.config.https.enabled else HTTPS_HELP,
        }
    )
    if ctx.agent.os == "windows":
        items.append({"name": "firewall", "label": "Firewall", "ok": None, "detail": FIREWALL_HELP})
    return items


def _autostart_state(ctx: DesktopContext) -> bool | None:
    if ctx.autostart is None:
        return None
    try:
        return ctx.autostart.is_enabled()
    except OSError:
        return None


def desktop_state(
    ctx: DesktopContext, lan_ip: str | None, moved: Move | None = None
) -> dict[str, Any]:
    agent = ctx.agent
    code, seconds_left = agent.pairing.current()
    https = agent.config.https.enabled
    url = pairing_url(lan_ip, ctx.port, code, https=https) if lan_ip is not None else None
    devices = []
    for d in agent.devices_state().devices:
        timing = agent.router.handling_ms(d.device_id)
        devices.append(
            {
                **d.model_dump(by_alias=True),
                "handlingMs": {"p50": timing[0], "p95": timing[1]} if timing else None,
            }
        )
    config = agent.config
    return {
        "version": __version__,
        "hostName": agent.host_name,
        "os": agent.os,
        "pairing": {
            "code": code,
            "secondsLeft": round(seconds_left),
            "url": url,
            "qrSvg": qr_svg(url) if url is not None else None,
        },
        "paused": config.remote_control_paused,
        "autostart": _autostart_state(ctx),
        "devices": devices,
        "firstRun": len(devices) == 0,
        # The laptop's Wi-Fi address changed: phones paired at the old one must pair again.
        "networkMoved": (
            {"from": moved.previous, "to": moved.current} if moved is not None and devices else None
        ),
        "checklist": _checklist(ctx),
        "settings": {
            "preferredBrowser": config.preferred_browser,
            "aiProvider": config.ai.provider,
            "aiModel": config.ai.model,
            "previewFps": config.preview.fps,
            "previewWidth": config.preview.width,
            "previewQuality": config.preview.quality,
        },
        "logsDir": str(agent.data_dir / "logs"),
    }


def apply_settings(config: Config, body: SettingsBody) -> Config:
    """A validated copy of ``config`` with the changes applied. Raises ValidationError."""
    data = config.model_dump(by_alias=True)
    if body.preferred_browser is not None:
        data["preferredBrowser"] = body.preferred_browser
    if body.ai_provider is not None:
        data["ai"]["provider"] = body.ai_provider
    if body.ai_model is not None:
        data["ai"]["model"] = body.ai_model
    for field, key in (
        ("preview_fps", "fps"),
        ("preview_width", "width"),
        ("preview_quality", "quality"),
    ):
        value = getattr(body, field)
        if value is not None:
            data["preview"][key] = value
    return Config.model_validate(data)


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def register_desktop(app: FastAPI, ctx: DesktopContext) -> None:
    agent = ctx.agent

    def network() -> NetworkWatch | None:
        return getattr(app.state, "network", None)

    @app.get("/desktop", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard(request: Request) -> HTMLResponse:
        _guard_read(request)
        nonce = secrets.token_urlsafe(16)
        html = DASHBOARD_HTML.replace("__NONCE__", nonce)
        return HTMLResponse(
            html,
            headers={
                "Content-Security-Policy": (
                    f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'none'"
                ),
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get("/desktop/api/state", include_in_schema=False)
    async def state(request: Request) -> JSONResponse:
        _guard_read(request)
        watch = network()
        return JSONResponse(
            desktop_state(ctx, watch.ip if watch else None, watch.moved if watch else None),
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/desktop/api/clipboard/send", include_in_schema=False)
    async def send_clipboard(request: Request) -> JSONResponse:
        _guard_write(request)
        try:
            phones = await ctx.services.clipboard.send_to_phones()
        except ActionError as exc:
            return _error(exc.message)
        if phones == 0:
            return _error("No owner phone is connected right now.")
        return JSONResponse({"ok": True, "phones": phones})

    @app.post("/desktop/api/pair/regenerate", include_in_schema=False)
    async def regenerate(request: Request) -> JSONResponse:
        _guard_write(request)
        agent.pairing.regenerate()
        log_event(log, "pair_code_regenerated")
        return JSONResponse({"ok": True})

    @app.post("/desktop/api/devices/{device_id}/revoke", include_in_schema=False)
    async def revoke(request: Request, device_id: str) -> JSONResponse:
        _guard_write(request)
        try:
            await agent.revoke_device(device_id, by=None)
        except ActionError as exc:
            return _error(exc.message)
        return JSONResponse({"ok": True})

    @app.post("/desktop/api/devices/{device_id}/role", include_in_schema=False)
    async def role(request: Request, device_id: str, body: RoleBody) -> JSONResponse:
        _guard_write(request)
        try:
            await agent.set_device_role(device_id, body.role)
        except ActionError as exc:
            return _error(exc.message)
        return JSONResponse({"ok": True})

    @app.post("/desktop/api/pause", include_in_schema=False)
    async def pause(request: Request, body: PauseBody) -> JSONResponse:
        _guard_write(request)
        await agent.set_paused(body.paused)
        return JSONResponse({"ok": True, "paused": agent.config.remote_control_paused})

    @app.post("/desktop/api/autostart", include_in_schema=False)
    async def autostart(request: Request, body: EnabledBody) -> JSONResponse:
        _guard_write(request)
        if ctx.autostart is None:
            return _error("Starting at login isn't available here.")
        try:
            ctx.autostart.enable() if body.enabled else ctx.autostart.disable()
        except OSError:
            return _error("Couldn't change the login setting.")
        log_event(log, "autostart", enabled=body.enabled)
        return JSONResponse({"ok": True, "enabled": _autostart_state(ctx)})

    @app.post("/desktop/api/settings", include_in_schema=False)
    async def settings(request: Request, body: SettingsBody) -> JSONResponse:
        _guard_write(request)
        try:
            updated = apply_settings(agent.config, body)
        except ValidationError:
            return _error("One of those values isn't allowed.")
        # Saved for the next start. The paused flag lives in the same file, so keep it current.
        updated.remote_control_paused = agent.config.remote_control_paused
        save_config(updated, agent.data_dir / CONFIG_FILENAME)
        log_event(log, "settings_saved")
        return JSONResponse({"ok": True, "message": SETTINGS_RESTART})
