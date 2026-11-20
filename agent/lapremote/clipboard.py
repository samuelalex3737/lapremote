"""Send to laptop and back: clipboard text both ways, and opening a link on the laptop.

Only text crosses the clipboard. It is never logged (only its length), never run, and capped at
MAX_CLIPBOARD_CHARS. Links go through the launcher, which only opens http(s) in the browser.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from typing import Protocol

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    MAX_CLIPBOARD_CHARS,
    ClipboardSet,
    ClipboardState,
    Empty,
    OsName,
    UrlOpen,
)
from lapremote.router import ActionError
from lapremote.shortcuts import Launcher, LaunchError

log = get_logger("clipboard")

OPEN_RETRIES = 10
OPEN_RETRY_SECONDS = 0.05
TOOL_TIMEOUT = 3


class ClipboardError(Exception):
    pass


class ClipboardBackend(Protocol):
    def get_text(self) -> str: ...
    def set_text(self, text: str) -> None: ...


class WindowsClipboard:
    """win32clipboard, retried briefly because another app may hold the clipboard open."""

    def _open(self) -> None:
        import win32clipboard  # noqa: PLC0415 - Windows only

        for _ in range(OPEN_RETRIES):
            try:
                win32clipboard.OpenClipboard()
            except Exception:  # pywintypes.error while another app has the clipboard open
                time.sleep(OPEN_RETRY_SECONDS)
            else:
                return
        msg = "the clipboard is busy"
        raise ClipboardError(msg)

    def get_text(self) -> str:
        import win32clipboard  # noqa: PLC0415
        import win32con  # noqa: PLC0415

        self._open()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return ""
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return str(data) if data else ""
        finally:
            win32clipboard.CloseClipboard()  # type: ignore[no-untyped-call]

    def set_text(self, text: str) -> None:
        import win32clipboard  # noqa: PLC0415
        import win32con  # noqa: PLC0415

        self._open()
        try:
            win32clipboard.EmptyClipboard()  # type: ignore[no-untyped-call]
            win32clipboard.SetClipboardText(  # type: ignore[no-untyped-call]
                text, win32con.CF_UNICODETEXT
            )
        finally:
            win32clipboard.CloseClipboard()  # type: ignore[no-untyped-call]


class ToolClipboard:
    """pbcopy/pbpaste (macOS), wl-copy/wl-paste or xclip (Linux). Fixed programs and args."""

    def __init__(self, copy: list[str], paste: list[str]) -> None:
        self._copy = copy
        self._paste = paste

    def get_text(self) -> str:
        try:
            result = subprocess.run(  # noqa: S603 - fixed tool and arguments
                self._paste, capture_output=True, timeout=TOOL_TIMEOUT, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ClipboardError(str(exc)) from exc
        return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else ""

    def set_text(self, text: str) -> None:
        try:
            result = subprocess.run(  # noqa: S603 - fixed tool and arguments; text on stdin
                self._copy, input=text.encode("utf-8"), timeout=TOOL_TIMEOUT, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ClipboardError(str(exc)) from exc
        if result.returncode != 0:
            msg = "the clipboard tool failed"
            raise ClipboardError(msg)


def create_clipboard(os_name: OsName) -> ClipboardBackend | None:
    if os_name == "windows" and sys.platform == "win32":
        return WindowsClipboard()
    if os_name == "macos":
        copy, paste = shutil.which("pbcopy"), shutil.which("pbpaste")
        return ToolClipboard([copy], [paste]) if copy and paste else None
    wl_copy, wl_paste = shutil.which("wl-copy"), shutil.which("wl-paste")
    if wl_copy and wl_paste:
        return ToolClipboard([wl_copy], [wl_paste, "--no-newline"])
    xclip = shutil.which("xclip")
    if xclip:
        return ToolClipboard(
            [xclip, "-selection", "clipboard", "-in"], [xclip, "-selection", "clipboard", "-out"]
        )
    return None


class ClipboardService:
    def __init__(self, agent: Agent, backend: ClipboardBackend | None, launcher: Launcher) -> None:
        self._agent = agent
        self._backend = backend
        self._launcher = launcher

    def register(self) -> None:
        router = self._agent.router
        router.register("clipboard.set", self._set)
        router.register("clipboard.get", self._get)
        router.register("url.open", self._open_url)

    def _require(self) -> ClipboardBackend:
        if self._backend is None:
            raise ActionError("The clipboard isn't available on this laptop.")
        return self._backend

    async def read(self) -> ClipboardState:
        backend = self._require()
        try:
            text = await asyncio.to_thread(backend.get_text)
        except ClipboardError as exc:
            raise ActionError("Couldn't read the laptop's clipboard. Try again.") from exc
        return ClipboardState(text=text[:MAX_CLIPBOARD_CHARS], ts=time.time() * 1000)

    async def _set(self, conn: Connection, p: ClipboardSet) -> None:
        backend = self._require()
        try:
            await asyncio.to_thread(backend.set_text, p.text)
        except ClipboardError as exc:
            raise ActionError("Couldn't use the laptop's clipboard. Try again.") from exc
        # Length only: clipboard text is the person's own.
        log_event(log, "clipboard_set", device=conn.device_id, textLength=len(p.text))

    async def _get(self, conn: Connection, _p: Empty) -> None:
        state = await self.read()
        log_event(log, "clipboard_get", device=conn.device_id, textLength=len(state.text))
        await conn.send("clipboard.state", state)

    async def _open_url(self, conn: Connection, p: UrlOpen) -> None:
        try:
            await asyncio.to_thread(self._launcher.open_url, p.url)
        except LaunchError as exc:
            raise ActionError("Couldn't open that link on the laptop.") from exc
        log_event(log, "url_opened", device=conn.device_id)

    async def send_to_phones(self) -> int:
        """Push the laptop clipboard to every owner phone. Returns how many got it."""
        state = await self.read()
        sent = 0
        for conn in self._agent.hub.authed():
            if conn.role == "owner" and await conn.send("clipboard.state", state):
                sent += 1
        log_event(log, "clipboard_sent", phones=sent, textLength=len(state.text))
        return sent
