"""What is in focus on the laptop: the foreground app, its window title, category and site.

``ContextService`` polls the foreground window every 500 ms and pushes
``context.state`` to phones only when it changes. Smart seek uses the same reader
to make sure keys only ever go to a browser that is in front.
"""

from __future__ import annotations

import asyncio
import contextlib
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

import psutil

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import now_ms
from lapremote.protocol import ContextCategory, ContextState, Site
from lapremote.system.platform_info import DisplayServer, detect_display_server, detect_os

log = get_logger("context")

POLL_SECONDS = 0.5

BROWSERS = {
    "brave": "Brave",
    "chrome": "Chrome",
    "msedge": "Edge",
    "edge": "Edge",
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
    "musicbee": "MusicBee",
    "rhythmbox": "Rhythmbox",
}
VIDEO_APPS = {
    "vlc": "VLC",
    "mpv": "mpv",
    "iina": "IINA",
    "netflix": "Netflix",
    "wmplayer": "Media Player",
    "quicktime": "QuickTime Player",
}
PRESENTATION_APPS = {
    "powerpnt": "PowerPoint",
    "powerpoint": "PowerPoint",
    "keynote": "Keynote",
    "soffice.bin": "Impress",
    "impress": "Impress",
}
DESKTOP_PROCESSES = {"explorer", "finder", "gnome-shell", "plasmashell", "dock"}

# Window-title patterns for sites (checked case-insensitively, first match wins).
SITE_PATTERNS: tuple[tuple[Site, re.Pattern[str]], ...] = (
    ("youtube", re.compile(r"\byoutube\b", re.IGNORECASE)),
    ("netflix", re.compile(r"\bnetflix\b", re.IGNORECASE)),
    ("prime", re.compile(r"\bprime video\b|\bamazon\.com.*video\b", re.IGNORECASE)),
    ("spotify_web", re.compile(r"\bspotify\b", re.IGNORECASE)),
)
SLIDES_PATTERN = re.compile(r"google slides|- slides\b", re.IGNORECASE)
_WORDS = re.compile(r"[\s._-]+")


@dataclass(frozen=True)
class ForegroundInfo:
    app: str
    process_name: str
    window_title: str
    category: ContextCategory
    site: Site | None


def _lookup(process: str, table: dict[str, str]) -> str | None:
    """Exact process name, or a whole word of it ("Brave Browser" -> brave)."""
    if process in table:
        return table[process]
    words = _WORDS.split(process)
    for word in words:
        if word in table:
            return table[word]
    return None


def classify(process_name: str, window_title: str) -> ForegroundInfo:
    process = process_name.lower().removesuffix(".exe").removesuffix(".app")
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
    tables: tuple[tuple[dict[str, str], ContextCategory], ...] = (
        (MUSIC_APPS, "music"),
        (VIDEO_APPS, "video"),
        (PRESENTATION_APPS, "presentation"),
    )
    for table, category in tables:
        app = _lookup(process, table)
        if app is not None:
            return ForegroundInfo(app, process_name, title, category, None)
    if process in DESKTOP_PROCESSES and not title:
        return ForegroundInfo("Desktop", process_name, title, "desktop", None)
    app = process_name.removesuffix(".exe")
    return ForegroundInfo(app[:1].upper() + app[1:], process_name, title, "other", None)


# ---------------------------------------------------------------- per-OS readers


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


def _mac_foreground() -> tuple[str, str] | None:
    """Frontmost app from NSWorkspace; its window title from the Quartz window list.

    macOS only reveals other apps' window titles once Screen Recording is allowed,
    so without it the title is empty and only the app is known.
    """
    import Quartz  # type: ignore[import-not-found,unused-ignore]  # noqa: PLC0415 - macOS only
    from AppKit import NSWorkspace  # type: ignore[import-not-found,unused-ignore]  # noqa: PLC0415

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    name = str(app.localizedName() or "")
    pid = int(app.processIdentifier())
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    title = ""
    for window in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
        if (
            int(window.get("kCGWindowOwnerPID", -1)) == pid
            and int(window.get("kCGWindowLayer", 1)) == 0
        ):
            title = str(window.get("kCGWindowName") or "")
            break
    return name, title


def parse_xdotool(name_out: str, pid_out: str) -> tuple[str, int] | None:
    try:
        pid = int(pid_out.strip())
    except ValueError:
        return None
    return name_out.strip(), pid


def _linux_foreground(xdotool: str) -> tuple[str, str] | None:
    """X11 only, through xdotool with fixed arguments."""

    def run(*args: str) -> str:
        result = subprocess.run(  # noqa: S603 - fixed executable and arguments
            [xdotool, *args], capture_output=True, text=True, timeout=1.0, check=False
        )
        return result.stdout if result.returncode == 0 else ""

    parsed = parse_xdotool(
        run("getactivewindow", "getwindowname"), run("getactivewindow", "getwindowpid")
    )
    if parsed is None:
        return None
    title, pid = parsed
    try:
        name = psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return name, title


ForegroundReader = Callable[[], "ForegroundInfo | None"]


def make_reader(
    system: str | None = None, display: DisplayServer | None = None
) -> ForegroundReader | None:
    """The foreground reader for this OS, or None where it can't work (for example Wayland)."""
    system = system or platform.system()
    if system == "Windows":
        return lambda: _classified(_windows_foreground())
    if system == "Darwin":
        return lambda: _classified(_mac_foreground())
    if system == "Linux":
        if (display or detect_display_server(detect_os())) != "x11":
            return None
        xdotool = shutil.which("xdotool")
        if xdotool is None:
            return None
        return lambda: _classified(_linux_foreground(xdotool))
    return None


def _classified(found: tuple[str, str] | None) -> ForegroundInfo | None:
    return classify(*found) if found is not None else None


def read_foreground() -> ForegroundInfo | None:
    """The foreground app right now, or None where this OS can't tell."""
    reader = make_reader()
    return reader() if reader is not None else None


# ---------------------------------------------------------------- service


def to_state(info: ForegroundInfo) -> ContextState:
    return ContextState(
        app=info.app,
        process_name=info.process_name,
        window_title=info.window_title[:300],
        category=info.category,
        site=info.site,
        ts=now_ms(),
    )


class ContextService:
    def __init__(
        self, agent: Agent, reader: ForegroundReader | None, interval: float = POLL_SECONDS
    ) -> None:
        self._agent = agent
        self._reader = reader
        self._interval = interval
        self._last: ForegroundInfo | None = None
        self._task: asyncio.Task[None] | None = None
        self._failures = 0

    def register(self) -> None:
        if self._reader is None:
            self._agent.set_feature(
                "context", False, "This laptop can't tell which app is in front."
            )
            return
        self._agent.set_feature("context", True)
        self._agent.on_connect.append(self._send)
        self._agent.on_startup.append(self.start)
        self._agent.on_shutdown.append(self.stop)

    @property
    def current(self) -> ForegroundInfo | None:
        return self._last

    async def start(self) -> None:
        await self.poll_once(broadcast=False)
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            # Nobody to tell: skip the read. A phone that connects gets a fresh read first.
            if self._agent.hub.authed():
                await self.poll_once()

    async def poll_once(self, *, broadcast: bool = True) -> None:
        reader = self._reader
        if reader is None:
            return
        try:
            info = await asyncio.to_thread(reader)
        except (OSError, subprocess.SubprocessError) as exc:
            self._failures += 1
            if self._failures == 1:
                log_event(log, "context_read_failed", level=30, error=str(exc))
            return
        self._failures = 0
        if info is None or info == self._last:
            return
        self._last = info
        if broadcast:
            await self._agent.hub.broadcast("context.state", to_state(info))

    async def _send(self, conn: Connection) -> None:
        await self.poll_once(broadcast=False)
        if self._last is not None:
            await conn.send("context.state", to_state(self._last))
