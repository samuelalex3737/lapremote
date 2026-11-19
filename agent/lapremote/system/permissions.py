"""OS permission checks that decide whether input injection can work."""

from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass

from lapremote.system.platform_info import DisplayServer, OsName

APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)

MAC_ACCESSIBILITY_HELP = (
    "Allow LapRemote to control your Mac: open System Settings, Privacy & Security, "
    "Accessibility, turn on the app running LapRemote (Terminal or LapRemote), then restart it."
)
WAYLAND_HELP = (
    "Mouse and keyboard control needs an X11 session on Linux. Log out, pick an Xorg session "
    "(for example 'Ubuntu on Xorg'), and log back in."
)
NO_DISPLAY_HELP = "No desktop session found. Start LapRemote from inside your desktop session."


@dataclass(frozen=True)
class InputPermission:
    available: bool
    reason: str | None


def mac_accessibility_trusted() -> bool:
    """AXIsProcessTrusted() from ApplicationServices, read through ctypes (no extra deps)."""
    if platform.system() != "Darwin":
        return False
    try:
        lib = ctypes.cdll.LoadLibrary(APPLICATION_SERVICES)
    except OSError:
        return False
    func = lib.AXIsProcessTrusted
    func.restype = ctypes.c_bool
    return bool(func())


def input_permission(
    os_name: OsName, display_server: DisplayServer | None, mac_trusted: bool
) -> InputPermission:
    if os_name == "macos" and not mac_trusted:
        return InputPermission(False, MAC_ACCESSIBILITY_HELP)
    if os_name == "linux":
        if display_server == "wayland":
            return InputPermission(False, WAYLAND_HELP)
        if display_server == "unknown":
            return InputPermission(False, NO_DISPLAY_HELP)
    return InputPermission(True, None)
