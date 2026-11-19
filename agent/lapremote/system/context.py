"""What is in focus on the laptop: the foreground app, its window title, category and site.

Phase 3 uses this for smart seek (keys only go to a browser in front). Phase 5 adds
polling and the context.state push.
"""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass

import psutil

from lapremote.protocol import ContextCategory, Site

BROWSERS = {
    "brave": "Brave",
    "chrome": "Chrome",
    "msedge": "Edge",
    "firefox": "Firefox",
    "opera": "Opera",
    "vivaldi": "Vivaldi",
    "safari": "Safari",
    "chromium": "Chromium",
    "arc": "Arc",
}
MUSIC_APPS = {
    "spotify": "Spotify",
    "music": "Music",
    "itunes": "iTunes",
    "foobar2000": "foobar2000",
}
VIDEO_APPS = {
    "vlc": "VLC",
    "mpv": "mpv",
    "iina": "IINA",
    "netflix": "Netflix",
    "wmplayer": "Media Player",
}
PRESENTATION_APPS = {"powerpnt": "PowerPoint", "keynote": "Keynote", "soffice.bin": "Impress"}
DESKTOP_PROCESSES = {"explorer", "finder", "gnome-shell", "plasmashell"}

# Window-title patterns for sites (checked case-insensitively, first match wins).
SITE_PATTERNS: tuple[tuple[Site, re.Pattern[str]], ...] = (
    ("youtube", re.compile(r"\byoutube\b", re.IGNORECASE)),
    ("netflix", re.compile(r"\bnetflix\b", re.IGNORECASE)),
    ("prime", re.compile(r"\bprime video\b|\bamazon\.com.*video\b", re.IGNORECASE)),
    ("spotify_web", re.compile(r"\bspotify\b", re.IGNORECASE)),
)
SLIDES_PATTERN = re.compile(r"google slides|- slides\b", re.IGNORECASE)


@dataclass(frozen=True)
class ForegroundInfo:
    app: str
    process_name: str
    window_title: str
    category: ContextCategory
    site: Site | None


def _lookup(process: str, table: dict[str, str]) -> str | None:
    return table.get(process)


def classify(process_name: str, window_title: str) -> ForegroundInfo:
    process = process_name.lower().removesuffix(".exe")
    title = window_title.strip()
    browser = _lookup(process, BROWSERS)
    if browser is not None:
        if SLIDES_PATTERN.search(title):
            return ForegroundInfo(browser, process_name, title, "presentation", None)
        site: Site | None = "generic"
        for name, pattern in SITE_PATTERNS:
            if pattern.search(title):
                site = name
                break
        return ForegroundInfo(browser, process_name, title, "browser", site)
    for table, category in (
        (MUSIC_APPS, "music"),
        (VIDEO_APPS, "video"),
        (PRESENTATION_APPS, "presentation"),
    ):
        app = _lookup(process, table)
        if app is not None:
            return ForegroundInfo(app, process_name, title, category, None)  # type: ignore[arg-type]
    if process in DESKTOP_PROCESSES and not title:
        return ForegroundInfo("Desktop", process_name, title, "desktop", None)
    app = process_name.removesuffix(".exe")
    return ForegroundInfo(app[:1].upper() + app[1:], process_name, title, "other", None)


def _windows_foreground() -> tuple[str, str] | None:
    import win32gui  # noqa: PLC0415 - Windows only
    import win32process  # noqa: PLC0415 - Windows only

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        name = psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return name, title


def read_foreground() -> ForegroundInfo | None:
    """The foreground app right now, or None where this OS isn't supported yet."""
    if platform.system() == "Windows":
        found = _windows_foreground()
        return classify(*found) if found is not None else None
    return None
