"""Print a recon report of the host: OS, toolchain, displays, DPI and media tools.

Run from the repo root:
    uv run --project agent python scripts/recon.py
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from dataclasses import dataclass

import mss

from lapremote.system.platform_info import detect_platform

# Windows MDT_EFFECTIVE_DPI for GetDpiForMonitor, and PROCESS_PER_MONITOR_DPI_AWARE.
_MDT_EFFECTIVE_DPI = 0
_PER_MONITOR_AWARE = 2
_BASE_DPI = 96


@dataclass(frozen=True)
class Display:
    index: int
    left: int
    top: int
    width: int
    height: int
    scale_percent: int | None


def tool_version(executable: str, flag: str = "--version") -> str:
    path = shutil.which(executable)
    if path is None:
        return "not found"
    result = subprocess.run(  # noqa: S603 - fixed executable resolved by which, fixed flag
        [path, flag], capture_output=True, text=True, timeout=20, check=False
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else f"exit code {result.returncode}"


def _windows_monitor_scales() -> list[int]:
    """Effective scale of each monitor, in EnumDisplayMonitors order."""
    from ctypes import wintypes  # noqa: PLC0415 - Windows-only import

    windll = ctypes.windll  # type: ignore[attr-defined,unused-ignore]
    windll.shcore.SetProcessDpiAwareness(_PER_MONITOR_AWARE)
    scales: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined,unused-ignore]
        ctypes.c_int,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def on_monitor(hmonitor: int, _hdc: int, _rect: object, _data: int) -> int:
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        windll.shcore.GetDpiForMonitor(
            hmonitor, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        scales.append(round(dpi_x.value * 100 / _BASE_DPI))
        return 1

    windll.user32.EnumDisplayMonitors(None, None, callback_type(on_monitor), 0)
    return scales


def detect_displays() -> list[Display]:
    scales = _windows_monitor_scales() if sys.platform == "win32" else []
    with mss.MSS() as grabber:
        monitors = grabber.monitors[1:]  # index 0 is the virtual union of all monitors
    displays: list[Display] = []
    for index, mon in enumerate(monitors):
        scale = scales[index] if index < len(scales) else None
        displays.append(Display(index, mon["left"], mon["top"], mon["width"], mon["height"], scale))
    return displays


def main() -> int:
    info = detect_platform()
    print("LapRemote recon")
    print(f"  OS:              {info.os_version} ({info.os}, {info.machine})")
    print(f"  Hostname:        {info.hostname}")
    print(f"  Python (agent):  {info.python_version}")
    print(f"  Node:            {tool_version('node')}")
    print(f"  npm:             {tool_version('npm')}")
    print(f"  uv:              {tool_version('uv')}")
    print(f"  git:             {tool_version('git')}")
    if info.media_cli is None:
        print("  Media backend:   built-in OS API (no CLI needed)")
    else:
        state = info.media_cli.path or "NOT INSTALLED"
        print(f"  Media CLI:       {info.media_cli.name} -> {state}")
    if info.display_server is not None:
        print(f"  Display server:  {info.display_server}")
    displays = detect_displays()
    print(f"  Displays:        {len(displays)}")
    for disp in displays:
        scale = f"{disp.scale_percent}%" if disp.scale_percent is not None else "not detected"
        print(
            f"    #{disp.index}: {disp.width}x{disp.height} physical px "
            f"at ({disp.left},{disp.top}), scale {scale}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
