"""Detect the host OS and the external tools each OS backend depends on."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

OsName = Literal["windows", "macos", "linux"]
DisplayServer = Literal["x11", "wayland", "unknown"]

# External CLI each OS uses for media sessions. Windows uses the built-in
# GSMTC API through winrt, so it has no CLI dependency.
MEDIA_CLI: dict[OsName, str | None] = {
    "windows": None,
    "macos": "media-control",
    "linux": "playerctl",
}


class UnsupportedPlatformError(RuntimeError):
    """LapRemote only runs on Windows, macOS and Linux."""


class ToolStatus(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    path: str | None

    @property
    def found(self) -> bool:
        return self.path is not None


class PlatformInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    os: OsName
    os_version: str
    machine: str
    python_version: str
    hostname: str
    media_cli: ToolStatus | None
    display_server: DisplayServer | None


def detect_os(sys_platform: str | None = None) -> OsName:
    value = sys.platform if sys_platform is None else sys_platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    if value.startswith("linux"):
        return "linux"
    msg = f"Unsupported platform: {value}"
    raise UnsupportedPlatformError(msg)


def os_version(os_name: OsName) -> str:
    if os_name == "windows":
        release, version, _csd, _ptype = platform.win32_ver()
        edition = platform.win32_edition() or ""
        return " ".join(part for part in (f"Windows {release}", edition, version) if part)
    if os_name == "macos":
        return f"macOS {platform.mac_ver()[0]}"
    try:
        pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
    except OSError:
        pretty = None
    return f"{pretty or 'Linux'} (kernel {platform.release()})"


def detect_display_server(
    os_name: OsName, env: dict[str, str] | None = None
) -> DisplayServer | None:
    """Linux only: input injection via pynput needs X11, so Wayland must be reported."""
    if os_name != "linux":
        return None
    values = os.environ if env is None else env
    session = values.get("XDG_SESSION_TYPE", "").lower()
    if session in ("x11", "wayland"):
        return "wayland" if session == "wayland" else "x11"
    if values.get("WAYLAND_DISPLAY"):
        return "wayland"
    if values.get("DISPLAY"):
        return "x11"
    return "unknown"


def detect_media_cli(os_name: OsName) -> ToolStatus | None:
    name = MEDIA_CLI[os_name]
    if name is None:
        return None
    return ToolStatus(name=name, path=shutil.which(name))


def detect_platform() -> PlatformInfo:
    os_name = detect_os()
    return PlatformInfo(
        os=os_name,
        os_version=os_version(os_name),
        machine=platform.machine(),
        python_version=platform.python_version(),
        hostname=socket.gethostname(),
        media_cli=detect_media_cli(os_name),
        display_server=detect_display_server(os_name),
    )
