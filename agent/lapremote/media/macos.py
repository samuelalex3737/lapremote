"""macOS now-playing through the `media-control` CLI (ungive/mediaremote-adapter).

Install: ``brew tap ungive/media-control && brew install media-control``. It works on
macOS 15.4+, where the private MediaRemote framework is no longer readable directly.

``media-control stream`` prints one JSON object per line:
``{"type": "data", "diff": bool, "payload": {...}}``. A full payload has keys such as
``bundleIdentifier``, ``title``, ``artist``, ``album``, ``duration``, ``elapsedTime``,
``timestamp``, ``playing``, ``playbackRate``, ``artworkData`` (base64). With
``diff: true`` only the changed keys are sent. An empty payload means nothing is playing.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
from datetime import datetime
from typing import Any

from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import (
    MediaBackend,
    MediaCommand,
    SessionSnapshot,
    friendly_app_name,
    now_ms,
    thumbnail_jpeg,
)

log = get_logger("media.macos")

SESSION_ID = "mac-now-playing"
COMMANDS: dict[MediaCommand, str] = {
    "toggle": "toggle-play-pause",
    "play": "play",
    "pause": "pause",
    "next": "next-track",
    "prev": "previous-track",
}
INSTALL_HELP = (
    "For track info on macOS, install media-control: "
    "brew tap ungive/media-control && brew install media-control"
)


def _parse_time(value: object) -> float:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
        except ValueError:
            return now_ms()
    if isinstance(value, (int, float)):
        # Seconds since 1970 or milliseconds: anything this big is already ms.
        return float(value) if value > 10_000_000_000 else float(value) * 1000
    return now_ms()


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def snapshot_from_payload(payload: dict[str, Any], artwork: bytes | None) -> SessionSnapshot | None:
    """Build the single macOS session from a merged media-control payload."""
    if not payload or not payload.get("title"):
        return None
    bundle = str(
        payload.get("bundleIdentifier") or payload.get("parentApplicationBundleIdentifier") or ""
    )
    playing = bool(payload.get("playing"))
    duration = _number(payload.get("duration"))
    elapsed = _number(payload.get("elapsedTime"))
    rate = _number(payload.get("playbackRate")) or 1.0
    snapshot = SessionSnapshot(
        id=SESSION_ID,
        app_id=bundle or "unknown",
        app_name=friendly_app_name(bundle) if bundle else "Now Playing",
        title=str(payload.get("title") or ""),
        artist=str(payload.get("artist") or ""),
        album=str(payload.get("album") or ""),
        status="playing" if playing else "paused",
        position=elapsed,
        duration=duration,
        rate=rate if playing else 1.0,
        can_seek=duration is not None and duration > 0,
        can_next=True,
        can_prev=True,
        updated_at=_parse_time(payload.get("timestamp")),
    )
    return snapshot.with_artwork(artwork)


class MacMediaBackend(MediaBackend):
    name = "media-control"

    def __init__(self, executable: str) -> None:
        super().__init__()
        self._exe = executable
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._payload: dict[str, Any] = {}
        self._artwork_b64: str | None = None
        self._artwork: bytes | None = None
        self._snapshot: SessionSnapshot | None = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._exe,
            "stream",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader = asyncio.get_running_loop().create_task(self._read())

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            with contextlib.suppress(ProcessLookupError):
                await self._proc.wait()

    async def _read(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        while True:
            line = await proc.stdout.readline()
            if not line:
                log_event(log, "stream_ended", level=30, code=proc.returncode)
                self._snapshot = None
                self._notify()
                return
            await self.apply_line(line)

    async def apply_line(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            return
        if not isinstance(message, dict) or message.get("type") != "data":
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        if message.get("diff"):
            self._payload.update(payload)
        else:
            self._payload = dict(payload)
        art = self._payload.get("artworkData")
        if art != self._artwork_b64:
            self._artwork_b64 = art if isinstance(art, str) else None
            self._artwork = await self._decode_artwork(self._artwork_b64)
        self._snapshot = snapshot_from_payload(self._payload, self._artwork)
        self._notify()

    @staticmethod
    async def _decode_artwork(data: str | None) -> bytes | None:
        if not data:
            return None
        try:
            raw = base64.b64decode(data, validate=False)
        except (binascii.Error, ValueError):
            return None
        return await asyncio.to_thread(thumbnail_jpeg, raw)

    def list_sessions(self) -> list[SessionSnapshot]:
        return [self._snapshot] if self._snapshot is not None else []

    def system_current_id(self) -> str | None:
        return SESSION_ID if self._snapshot is not None else None

    async def _run(self, *args: str) -> bool:
        proc = await asyncio.create_subprocess_exec(
            self._exe, *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        return await proc.wait() == 0

    async def command(self, session_id: str, action: MediaCommand) -> bool:
        if session_id != SESSION_ID:
            return False
        return await self._run(COMMANDS[action])

    async def seek_to(self, session_id: str, seconds: float) -> bool:
        if session_id != SESSION_ID:
            return False
        # The argument is a number we format ourselves, never text from the phone.
        return await self._run("seek", f"{max(0.0, seconds):.3f}")
