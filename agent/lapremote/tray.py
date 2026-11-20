"""System tray icon (pystray). The menu is plain data so it can be tested without a desktop.

The tray runs on the main thread. The agent's event loop runs in the server thread, so
every change goes through ``asyncio.run_coroutine_threadsafe``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from lapremote.autostart import Autostart
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event

log = get_logger("tray")

ICON_PATH = Path(__file__).parent / "static" / "icons" / "icon-192.png"
ACCENT = (124, 156, 255, 255)


def open_folder(path: Path) -> None:
    """Show a folder in the file manager. The path is always LapRemote's own data folder."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - our own folder, no shell
    elif sys.platform == "darwin":
        subprocess.Popen(["/usr/bin/open", str(path)])  # noqa: S603 - fixed program
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607 - fixed program


def tray_image() -> Image.Image:
    """The app icon from the web build, or a simple drawn one when the build isn't there."""
    if ICON_PATH.is_file():
        with Image.open(ICON_PATH) as image:
            return image.convert("RGBA").resize((64, 64))
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=16, fill=ACCENT)
    draw.rounded_rectangle((20, 14, 44, 50), radius=6, outline=(11, 13, 18, 255), width=4)
    return image


@dataclass
class MenuEntry:
    label: str
    action: Callable[[], None]
    checked: Callable[[], bool] | None = None
    enabled: Callable[[], bool] | None = None
    default: bool = False


class TrayController:
    def __init__(
        self,
        agent: Agent,
        port: int,
        autostart: Autostart | None,
        stop: Callable[[], None],
        *,
        open_url: Callable[[str], object] = webbrowser.open,
        show_folder: Callable[[Path], None] = open_folder,
        send_clipboard: Callable[[], Coroutine[Any, Any, int]] | None = None,
    ) -> None:
        self.agent = agent
        self.port = port
        self.autostart = autostart
        self._stop = stop
        self._open_url = open_url
        self._show_folder = show_folder
        self._send_clipboard = send_clipboard
        self.loop: asyncio.AbstractEventLoop | None = None

    def dashboard_url(self, section: str = "") -> str:
        scheme = "https" if self.agent.config.https.enabled else "http"
        suffix = f"#{section}" if section else ""
        return f"{scheme}://127.0.0.1:{self.port}/desktop{suffix}"

    def _run(self, coro: Coroutine[Any, Any, None]) -> None:
        if self.loop is None:
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=5)

    def open_dashboard(self) -> None:
        self._open_url(self.dashboard_url())

    def open_pairing(self) -> None:
        self._open_url(self.dashboard_url("pair-title"))

    def open_devices(self) -> None:
        self._open_url(self.dashboard_url("devices-title"))

    def paused(self) -> bool:
        return self.agent.config.remote_control_paused

    def toggle_pause(self) -> None:
        self._run(self.agent.set_paused(not self.paused()))

    def autostart_supported(self) -> bool:
        return self.autostart is not None

    def autostart_enabled(self) -> bool:
        if self.autostart is None:
            return False
        try:
            return self.autostart.is_enabled()
        except OSError:
            return False

    def toggle_autostart(self) -> None:
        if self.autostart is None:
            return
        try:
            if self.autostart_enabled():
                self.autostart.disable()
            else:
                self.autostart.enable()
        except OSError as exc:
            log_event(log, "autostart_failed", level=40, error=str(exc))
            return
        log_event(log, "autostart", enabled=self.autostart_enabled())

    def send_clipboard(self) -> None:
        """Push the laptop clipboard to the owner phones (shows on the phone)."""
        if self._send_clipboard is None or self.loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_clipboard(), self.loop).result(timeout=5)
        except Exception as exc:
            log_event(log, "tray_clipboard_failed", level=30, error=type(exc).__name__)

    def open_logs(self) -> None:
        self._show_folder(self.agent.data_dir / "logs")

    def quit(self) -> None:
        log_event(log, "quit_from_tray")
        self._stop()


def menu_entries(ctl: TrayController) -> list[MenuEntry]:
    return [
        MenuEntry("Pair a phone...", ctl.open_pairing, default=True),
        MenuEntry("Devices...", ctl.open_devices),
        MenuEntry("Pause remote control", ctl.toggle_pause, checked=ctl.paused),
        MenuEntry("Open dashboard", ctl.open_dashboard),
        MenuEntry("Send clipboard to phone", ctl.send_clipboard),
        MenuEntry(
            "Start at login",
            ctl.toggle_autostart,
            checked=ctl.autostart_enabled,
            enabled=ctl.autostart_supported,
        ),
        MenuEntry("Open logs folder", ctl.open_logs),
        MenuEntry("Quit LapRemote", ctl.quit),
    ]


def build_icon(ctl: TrayController) -> Any:  # noqa: ANN401 - pystray has no type hints
    """The tray icon. Call ``.run()`` on the main thread; ``ctl.quit`` should call ``.stop()``."""
    import pystray  # noqa: PLC0415 - needs a desktop session, imported only when used

    def item(entry: MenuEntry) -> Any:  # noqa: ANN401
        def act(_icon: object, _item: object) -> None:
            entry.action()

        kwargs: dict[str, Any] = {"default": entry.default}
        if entry.checked is not None:
            check = entry.checked
            kwargs["checked"] = lambda _item: check()
        if entry.enabled is not None:
            enabled = entry.enabled
            kwargs["enabled"] = lambda _item: enabled()
        return pystray.MenuItem(entry.label, act, **kwargs)

    items = [item(e) for e in menu_entries(ctl)]
    # A separator before Quit.
    menu = pystray.Menu(*items[:-1], pystray.Menu.SEPARATOR, items[-1])
    return pystray.Icon("LapRemote", tray_image(), "LapRemote", menu)
