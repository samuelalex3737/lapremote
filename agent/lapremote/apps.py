"""Installed apps: the list a shortcut can pick from, Store-app ids, and each app's own icon.

Windows: the Start menu's "AppsFolder" lists every installed app (desktop and Microsoft Store)
with a parsing name that ``shell:AppsFolder\\<id>`` opens. Store apps can't be started from their
``.exe`` (Windows says "Access is denied"), so a pasted ``...\\WindowsApps\\...\\App.exe`` path is
converted to the app's id.

macOS: ``.app`` bundles in /Applications and ~/Applications. Linux: ``.desktop`` files.
Only ids from this list (or validated paths) are ever launched.
"""

from __future__ import annotations

import asyncio
import base64
import io
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PIL import Image

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import AppInfo, AppsState, Empty, OsName

log = get_logger("apps")

ICON_PX = 96
LIST_TTL_SECONDS = 60.0
MAX_APPS = 600
WINDOWS_APPS_DIR = "\\windowsapps\\"
# <Name>_<Version>_<Arch>_<ResourceId>_<PublisherId>, e.g.
# SpotifyAB.SpotifyMusic_1.310.2586.0_x64__zpdnekdrzrea0
PACKAGE_FOLDER = re.compile(
    r"^(?P<name>[^_]+)_(?P<version>[^_]+)_(?P<arch>[^_]*)_(?P<res>[^_]*)_(?P<publisher>[a-z0-9]{13})$"
)
APP_ENTRY = re.compile(
    r"<Application\b[^>]*\bId=\"(?P<id>[^\"]+)\"[^>]*"
    r"\bExecutable=\"(?P<exe>[^\"]+)\"",
    re.IGNORECASE,
)


def png_data_url(image: Image.Image, size: int = ICON_PX) -> str:
    """Fit an image into a transparent square and return it as a small PNG data URL."""
    img = image.convert("RGBA")
    # Scale to fit the square both ways: small favicons are enlarged, big icons shrunk.
    scale = size / max(img.width, img.height)
    img = img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


class AppSource(Protocol):
    def list_apps(self) -> list[AppInfo]: ...
    def icon(self, target: str) -> str | None: ...


class NoApps:
    def list_apps(self) -> list[AppInfo]:
        return []

    def icon(self, target: str) -> str | None:
        return None


class WindowsApps:
    """AppsFolder through COM. Each call runs on a worker thread with its own COM apartment."""

    def list_apps(self) -> list[AppInfo]:
        import pythoncom  # noqa: PLC0415 - Windows only
        import win32com.client  # noqa: PLC0415

        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            items = shell.NameSpace("shell:AppsFolder").Items()
            apps: dict[str, AppInfo] = {}
            for i in range(min(items.Count, MAX_APPS)):
                item = items.Item(i)
                name, app_id = str(item.Name).strip(), str(item.Path).strip()
                if not name or not app_id or len(app_id) > 512 or len(name) > 128:
                    continue
                apps.setdefault(app_id, AppInfo(app_id=app_id, name=name))
            return sorted(apps.values(), key=lambda a: a.name.lower())
        finally:
            pythoncom.CoUninitialize()

    def icon(self, target: str) -> str | None:
        from lapremote.win_icons import shell_item_icon  # noqa: PLC0415 - Windows only

        name = target if Path(target).is_absolute() else "shell:AppsFolder\\" + target
        image = shell_item_icon(name, ICON_PX)
        return png_data_url(image) if image is not None else None


class MacApps:
    def list_apps(self) -> list[AppInfo]:
        roots = [Path("/Applications"), Path.home() / "Applications"]
        apps = [
            AppInfo(app_id=str(p), name=p.stem)
            for root in roots
            if root.is_dir()
            for p in sorted(root.glob("*.app"))
        ]
        return apps[:MAX_APPS]

    def icon(self, target: str) -> str | None:
        return None


class LinuxApps:
    DIRS = (
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
    )

    def list_apps(self) -> list[AppInfo]:
        apps: list[AppInfo] = []
        for root in self.DIRS:
            if not root.is_dir():
                continue
            for desktop in sorted(root.glob("*.desktop")):
                name = _desktop_name(desktop)
                if name is not None:
                    apps.append(AppInfo(app_id=str(desktop), name=name[:128]))
        return apps[:MAX_APPS]

    def icon(self, target: str) -> str | None:
        return None


def _desktop_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "NoDisplay=true" in text:
        return None
    match = re.search(r"^Name=(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def create_app_source(os_name: OsName) -> AppSource:
    if os_name == "windows":
        return WindowsApps()
    if os_name == "macos":
        return MacApps()
    return LinuxApps()


def store_app_id(path: str, installed: list[AppInfo]) -> str | None:
    """The app id for an exe inside ``WindowsApps`` (a Microsoft Store app), if installed."""
    lower = path.lower()
    if WINDOWS_APPS_DIR not in lower:
        return None
    folder = Path(path).parent
    while folder.parent != folder and folder.parent.name.lower() != "windowsapps":
        folder = folder.parent
    match = PACKAGE_FOLDER.match(folder.name)
    if match is None:
        return None
    family = f"{match['name']}_{match['publisher']}!"
    candidates = [a for a in installed if a.app_id.startswith(family)]
    if not candidates:
        return None
    exe = Path(path).name.lower()
    manifest = folder / "AppxManifest.xml"
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for entry in APP_ENTRY.finditer(text):
        if Path(entry["exe"]).name.lower() == exe:
            wanted = family + entry["id"]
            for app in candidates:
                if app.app_id == wanted:
                    return app.app_id
    # The exe isn't an app entry of its own (Spotify.exe is started by a launcher): use the
    # package's app that the Start menu shows.
    return candidates[0].app_id


class AppsService:
    def __init__(
        self,
        agent: Agent,
        source: AppSource,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._agent = agent
        self._source = source
        self._clock = clock
        self._cache: list[AppInfo] | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def source(self) -> AppSource:
        return self._source

    def register(self) -> None:
        self._agent.router.register("apps.list", self._list)

    async def installed(self) -> list[AppInfo]:
        async with self._lock:
            fresh = self._cache is not None and self._clock() - self._cached_at < LIST_TTL_SECONDS
            if not fresh:
                try:
                    self._cache = await asyncio.to_thread(self._source.list_apps)
                except Exception as exc:
                    log_event(log, "apps_list_failed", level=30, error=type(exc).__name__)
                    self._cache = self._cache or []
                self._cached_at = self._clock()
            return list(self._cache or [])

    async def icon(self, target: str) -> str | None:
        try:
            return await asyncio.to_thread(self._source.icon, target)
        except Exception as exc:
            log_event(log, "app_icon_failed", level=20, error=type(exc).__name__)
            return None

    async def _list(self, conn: Connection, _p: Empty) -> None:
        await conn.send("apps.state", AppsState(apps=await self.installed()))


def is_installed_id(target: str) -> bool:
    """True when ``target`` looks like an app id rather than a file path."""
    return not Path(target).is_absolute() and "\n" not in target
