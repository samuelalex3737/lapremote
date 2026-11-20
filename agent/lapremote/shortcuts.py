"""Launcher shortcuts: http(s) URLs and registered apps. Never command lines.

Shortcuts live in ~/.lapremote/shortcuts.json (seeded from
shared/shortcuts.default.json). A URL opens in the preferred browser (Brave when
installed); an app opens by its stored path or macOS bundle id, with no arguments.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from lapremote.apps import AppsService, is_installed_id, store_app_id
from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    LaunchOpen,
    OsName,
    Shortcut,
    ShortcutsDelete,
    ShortcutsReorder,
    ShortcutsSave,
    ShortcutsState,
)
from lapremote.router import ActionError
from lapremote.storage import load_or_seed, write_json_atomic

log = get_logger("launcher")

MAX_SHORTCUTS = 60
WINDOWS_APP_SUFFIXES = frozenset({".exe", ".lnk", ".url", ".appref-ms"})
BUNDLE_ID = re.compile(r"^[A-Za-z0-9]+(\.[A-Za-z0-9-]+)+$")
_LIST = TypeAdapter(list[Shortcut])


class LaunchError(Exception):
    """The browser or app could not be started."""


def validate_app_target(os_name: OsName, target: str) -> str:
    """Normalise an app target or raise ValueError with a friendly reason."""
    value = target.strip()
    if os_name == "macos" and BUNDLE_ID.match(value) and not value.startswith("/"):
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        msg = "Use the full path to the app on the laptop."
        raise ValueError(msg)
    if not path.exists():
        msg = "That app path doesn't exist on this laptop."
        raise ValueError(msg)
    if os_name == "windows":
        if path.suffix.lower() not in WINDOWS_APP_SUFFIXES:
            msg = "Pick an .exe or a shortcut (.lnk) file."
            raise ValueError(msg)
    elif os_name == "macos":
        if path.suffix != ".app":
            msg = "Pick an .app from Applications, or use its bundle id."
            raise ValueError(msg)
    elif not (path.suffix == ".desktop" or (path.is_file() and os.access(path, os.X_OK))):
        msg = "Pick a .desktop file or an executable program."
        raise ValueError(msg)
    return str(path)


class Launcher(Protocol):
    def open_url(self, url: str) -> None: ...
    def open_app(self, target: str) -> None: ...


def _windows_browser(name: str) -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    programs = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]
    relative = {
        "brave": r"BraveSoftware\Brave-Browser\Application\brave.exe",
        "chrome": r"Google\Chrome\Application\chrome.exe",
        "edge": r"Microsoft\Edge\Application\msedge.exe",
        "firefox": r"Mozilla Firefox\firefox.exe",
    }.get(name)
    if relative is None:
        return None
    for root in [local, *programs]:
        if root and (Path(root) / relative).is_file():
            return str(Path(root) / relative)
    return None


class SystemLauncher:
    """Starts browsers and apps with fixed executables and a single validated argument."""

    def __init__(self, os_name: OsName, preferred_browser: str) -> None:
        self._os = os_name
        self._browser = preferred_browser.lower()

    def _popen(self, args: list[str]) -> None:
        try:
            subprocess.Popen(  # noqa: S603 - fixed executable, one validated argument, no shell
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True
            )
        except OSError as exc:
            raise LaunchError(str(exc)) from exc

    def open_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            msg = "only http(s) URLs can be opened"
            raise LaunchError(msg)
        if self._os == "windows":
            exe = _windows_browser(self._browser) or _windows_browser("brave")
            if exe is not None:
                self._popen([exe, url])
                return
        elif self._os == "macos":
            app = {
                "brave": "Brave Browser",
                "chrome": "Google Chrome",
                "edge": "Microsoft Edge",
            }.get(self._browser, "Brave Browser")
            if Path(f"/Applications/{app}.app").exists():
                self._popen(["/usr/bin/open", "-a", app, url])
                return
            self._popen(["/usr/bin/open", url])
            return
        else:
            for name in ("brave-browser", "brave", self._browser):
                exe = shutil.which(name)
                if exe is not None:
                    self._popen([exe, url])
                    return
        if not webbrowser.open(url):
            msg = "no browser could be opened"
            raise LaunchError(msg)

    def open_app(self, target: str) -> None:
        if self._os == "windows":
            start = getattr(os, "startfile", None)
            if start is None:
                msg = "os.startfile is unavailable"
                raise LaunchError(msg)
            if is_installed_id(target):
                # An installed app's id (a Store app or a registered desktop app).
                target = "shell:AppsFolder\\" + target
            try:
                start(target)
            except OSError as exc:
                raise LaunchError(str(exc)) from exc
            return
        if self._os == "macos":
            if target.startswith("/"):
                self._popen(["/usr/bin/open", target])
            else:
                self._popen(["/usr/bin/open", "-b", target])
            return
        if target.endswith(".desktop"):
            gio = shutil.which("gio")
            if gio is None:
                msg = "gio is not installed"
                raise LaunchError(msg)
            self._popen([gio, "launch", target])
            return
        self._popen([target])


class ShortcutStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        try:
            self._items = _LIST.validate_python(load_or_seed(path, "shortcuts.default.json"))
        except ValidationError:
            path.replace(path.with_suffix(".json.broken"))
            self._items = _LIST.validate_python(load_or_seed(path, "shortcuts.default.json"))

    def items(self) -> list[Shortcut]:
        return list(self._items)

    def get(self, shortcut_id: str) -> Shortcut | None:
        return next((s for s in self._items if s.id == shortcut_id), None)

    def _save(self) -> None:
        write_json_atomic(
            self._path, [s.model_dump(mode="json", by_alias=True) for s in self._items]
        )

    def upsert(self, shortcut: Shortcut) -> None:
        for i, existing in enumerate(self._items):
            if existing.id == shortcut.id:
                self._items[i] = shortcut
                self._save()
                return
        if len(self._items) >= MAX_SHORTCUTS:
            msg = "too many shortcuts"
            raise OverflowError(msg)
        self._items.append(shortcut)
        self._save()

    def delete(self, shortcut_id: str) -> bool:
        before = len(self._items)
        self._items = [s for s in self._items if s.id != shortcut_id]
        if len(self._items) != before:
            self._save()
            return True
        return False

    def reorder(self, ids: list[str]) -> None:
        position = {sid: i for i, sid in enumerate(ids)}
        self._items.sort(key=lambda s: position.get(s.id, len(ids)))
        self._save()


IconFetcher = Callable[[str], Awaitable[str | None]]


class ShortcutService:
    def __init__(
        self,
        agent: Agent,
        store: ShortcutStore,
        launcher: Launcher,
        apps: AppsService | None = None,
        site_icon: IconFetcher | None = None,
    ) -> None:
        self._agent = agent
        self._store = store
        self._launcher = launcher
        self._apps = apps
        self._site_icon = site_icon

    @property
    def store(self) -> ShortcutStore:
        return self._store

    def register(self) -> None:
        self._agent.set_feature("launcher", True)
        router = self._agent.router
        router.register("launch.open", self._open)
        router.register("shortcuts.save", self._save)
        router.register("shortcuts.delete", self._delete)
        router.register("shortcuts.reorder", self._reorder)
        self._agent.on_connect.append(self._send_state)
        self._agent.on_startup.append(self._backfill_icons)

    def state(self) -> ShortcutsState:
        return ShortcutsState(shortcuts=self._store.items())

    async def _send_state(self, conn: Connection) -> None:
        await conn.send("shortcuts.state", self.state())

    async def _broadcast(self) -> None:
        await self._agent.hub.broadcast("shortcuts.state", self.state())

    async def launch(self, shortcut_id: str) -> Shortcut:
        shortcut = self._store.get(shortcut_id)
        if shortcut is None:
            raise ActionError("That shortcut doesn't exist anymore.")
        if shortcut.kind == "app" and shortcut.app is not None:
            shortcut = await self._upgrade_store_path(shortcut)
        try:
            if shortcut.kind == "url" and shortcut.url is not None:
                self._launcher.open_url(shortcut.url)
            elif shortcut.app is not None:
                self._launcher.open_app(shortcut.app)
        except LaunchError as exc:
            log_event(log, "launch_failed", level=30, shortcut=shortcut.id, error=str(exc))
            raise ActionError(f"Couldn't open {shortcut.name}.") from exc
        log_event(log, "launched", shortcut=shortcut.id, kind=shortcut.kind)
        return shortcut

    async def _open(self, _conn: Connection, p: LaunchOpen) -> None:
        await self.launch(p.shortcut_id)

    async def _resolve_app(self, target: str) -> str:
        """A launchable, validated app target: an installed app's id or a checked path."""
        value = target.strip()
        if self._agent.os == "windows" and self._apps is not None:
            installed = await self._apps.installed()
            store_id = store_app_id(value, installed)
            if store_id is not None:
                return store_id
            if is_installed_id(value):
                if any(app.app_id == value for app in installed):
                    return value
                raise ActionError("That app isn't installed on this laptop.")
        try:
            return validate_app_target(self._agent.os, value)
        except ValueError as exc:
            raise ActionError(str(exc)) from exc

    async def _upgrade_store_path(self, shortcut: Shortcut) -> Shortcut:
        """Store apps won't start from their .exe: switch an old saved path to the app id."""
        if self._agent.os != "windows" or self._apps is None or shortcut.app is None:
            return shortcut
        store_id = store_app_id(shortcut.app, await self._apps.installed())
        if store_id is None:
            return shortcut
        upgraded = shortcut.model_copy(update={"app": store_id})
        self._store.upsert(upgraded)
        log_event(log, "shortcut_upgraded", shortcut=shortcut.id)
        await self._broadcast()
        return upgraded

    async def _save(self, _conn: Connection, p: ShortcutsSave) -> None:
        shortcut = p.shortcut
        if shortcut.kind == "app" and shortcut.app is not None:
            shortcut = shortcut.model_copy(update={"app": await self._resolve_app(shortcut.app)})
        # The icon image is the agent's own work and never taken from a phone. Keep the stored
        # one while the target is unchanged, otherwise make a new one in the background.
        previous = self._store.get(shortcut.id)
        same_target = (
            previous is not None
            and previous.kind == shortcut.kind
            and previous.url == shortcut.url
            and previous.app == shortcut.app
        )
        image = previous.image if (same_target and previous is not None) else None
        shortcut = shortcut.model_copy(update={"image": image})
        try:
            self._store.upsert(shortcut)
        except OverflowError as exc:
            raise ActionError(f"You can have up to {MAX_SHORTCUTS} shortcuts.") from exc
        await self._broadcast()
        if image is None and shortcut.icon is None:
            self._agent.spawn(self.fill_icon(shortcut.id))

    async def make_icon(self, shortcut: Shortcut) -> str | None:
        if shortcut.kind == "url" and shortcut.url is not None and self._site_icon is not None:
            return await self._site_icon(shortcut.url)
        if shortcut.kind == "app" and shortcut.app is not None and self._apps is not None:
            return await self._apps.icon(shortcut.app)
        return None

    async def fill_icon(self, shortcut_id: str) -> None:
        """Make and store the icon image for one shortcut, then tell the phones."""
        shortcut = self._store.get(shortcut_id)
        if shortcut is None or shortcut.icon is not None:
            return
        image = await self.make_icon(shortcut)
        current = self._store.get(shortcut_id)
        # Saved again with another target while we worked: that save makes its own icon.
        if image is None or current is None:
            return
        if (current.url, current.app) != (shortcut.url, shortcut.app):
            return
        self._store.upsert(current.model_copy(update={"image": image}))
        log_event(log, "shortcut_icon", shortcut=shortcut_id, kind=current.kind)
        await self._broadcast()

    async def _backfill_icons(self) -> None:
        async def run() -> None:
            for shortcut in self._store.items():
                if shortcut.icon is None and shortcut.image is None and shortcut.id != "_once":
                    await self.fill_icon(shortcut.id)

        self._agent.spawn(run())

    async def _delete(self, _conn: Connection, p: ShortcutsDelete) -> None:
        if not self._store.delete(p.shortcut_id):
            raise ActionError("That shortcut doesn't exist anymore.")
        await self._broadcast()

    async def _reorder(self, _conn: Connection, p: ShortcutsReorder) -> None:
        self._store.reorder(p.ids)
        await self._broadcast()


def create_launcher(os_name: OsName, preferred_browser: str) -> Launcher:
    return SystemLauncher(os_name, preferred_browser)
