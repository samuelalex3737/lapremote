"""Make the process DPI aware on Windows so cursor coordinates are physical pixels.

Without this, Windows scales coordinates for 125%/150% displays and they no
longer match what mss captures (Phase 6 tap-to-click depends on that match).
"""

from __future__ import annotations

import ctypes
import sys

PROCESS_PER_MONITOR_DPI_AWARE = 2
E_ACCESSDENIED = 0x80070005
_state: dict[str, str] = {}


def enable_dpi_awareness() -> str:
    """Returns how awareness was set: per_monitor, system, already, unsupported or not_windows."""
    if "result" not in _state:
        _state["result"] = _enable()
    return _state["result"]


def _call(name: str, *args: int) -> int | None:
    windll = ctypes.windll  # type: ignore[attr-defined,unused-ignore]
    library, _, function = name.partition(".")
    try:
        result: int = getattr(getattr(windll, library), function)(*args)
    except (AttributeError, OSError):
        return None
    return result


def _enable() -> str:
    if sys.platform != "win32":
        return "not_windows"
    hr = _call("shcore.SetProcessDpiAwareness", PROCESS_PER_MONITOR_DPI_AWARE)
    if hr == 0:
        return "per_monitor"
    if hr is not None and (hr & 0xFFFFFFFF) == E_ACCESSDENIED:
        # Awareness was already set for this process (for example by mss).
        return "already"
    if _call("user32.SetProcessDPIAware"):
        return "system"
    return "unsupported"
