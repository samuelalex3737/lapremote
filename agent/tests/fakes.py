"""Test doubles for media and volume backends."""

from __future__ import annotations

import asyncio
import io
from dataclasses import replace

from PIL import Image

from lapremote.media.base import MediaBackend, MediaCommand, SessionSnapshot, now_ms, thumbnail_jpeg
from lapremote.system.volume import VolumeError


def jpeg(color: tuple[int, int, int] = (200, 30, 30), size: int = 400) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (size, size), color).save(out, format="PNG")
    result = thumbnail_jpeg(out.getvalue())
    assert result is not None
    return result


def session(
    sid: str = "w1",
    *,
    title: str = "Song",
    status: str = "playing",
    position: float | None = 30.0,
    duration: float | None = 200.0,
    can_seek: bool = True,
    art: bytes | None = None,
    app_id: str = "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
) -> SessionSnapshot:
    snap = SessionSnapshot(
        id=sid,
        app_id=app_id,
        app_name="Spotify",
        title=title,
        artist="Artist",
        album="Album",
        status=status,  # type: ignore[arg-type]
        position=position,
        duration=duration,
        rate=1.0,
        can_seek=can_seek,
        can_next=True,
        can_prev=True,
        updated_at=now_ms(),
    )
    return snap.with_artwork(art)


class FakeMediaBackend(MediaBackend):
    name = "fake"

    def __init__(self, sessions: list[SessionSnapshot] | None = None) -> None:
        super().__init__()
        self.sessions = list(sessions or [])
        self.current_session: str | None = self.sessions[0].id if self.sessions else None
        self.commands: list[tuple[str, MediaCommand]] = []
        self.seeks: list[tuple[str, float]] = []
        self.accept = True
        self.started = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self.started = True
        self._loop = asyncio.get_running_loop()

    async def stop(self) -> None:
        self.started = False

    def set_sessions(self, sessions: list[SessionSnapshot]) -> None:
        """Called from the test thread: notify on the app's own event loop."""
        self.sessions = list(sessions)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._notify)

    def list_sessions(self) -> list[SessionSnapshot]:
        return list(self.sessions)

    def system_current_id(self) -> str | None:
        return self.current_session

    async def command(self, session_id: str, action: MediaCommand) -> bool:
        self.commands.append((session_id, action))
        return self.accept

    async def seek_to(self, session_id: str, seconds: float) -> bool:
        self.seeks.append((session_id, seconds))
        self.sessions = [
            replace(s, position=seconds) if s.id == session_id else s for s in self.sessions
        ]
        return self.accept


class FakeVolume:
    name = "fake"

    def __init__(self, level: int = 40, muted: bool = False) -> None:
        self.level = level
        self.muted = muted
        self.broken = False
        self.sets: list[int] = []

    async def get(self) -> tuple[int, bool]:
        if self.broken:
            raise VolumeError("device gone")
        return self.level, self.muted

    async def set_level(self, level: int) -> None:
        self.sets.append(level)
        self.level = level

    async def set_muted(self, muted: bool) -> None:
        self.muted = muted
