"""MediaBackend ABC and the session snapshot every backend produces."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Literal

from PIL import Image, UnidentifiedImageError

from lapremote.protocol import MediaSession, MediaStatus

MediaCommand = Literal["toggle", "play", "pause", "next", "prev"]
ARTWORK_MAX_PX = 256
ARTWORK_QUALITY = 80


def now_ms() -> float:
    return time.time() * 1000


@dataclass(frozen=True)
class SessionSnapshot:
    id: str
    app_id: str
    app_name: str
    title: str
    artist: str
    album: str
    status: MediaStatus
    position: float | None
    duration: float | None
    rate: float
    can_seek: bool
    can_next: bool
    can_prev: bool
    updated_at: float
    artwork_id: str | None = None
    artwork_jpeg: bytes | None = None

    def position_now(self, at_ms: float | None = None) -> float | None:
        """Position interpolated to ``at_ms`` (or now) from ``updated_at`` and ``rate``."""
        if self.position is None:
            return None
        if self.status != "playing":
            return self.position
        elapsed = max(0.0, ((at_ms if at_ms is not None else now_ms()) - self.updated_at) / 1000)
        value = self.position + elapsed * self.rate
        if self.duration is not None:
            value = min(value, self.duration)
        return value

    def to_wire(self, include_artwork: bool) -> MediaSession:
        artwork = None
        if include_artwork and self.artwork_jpeg is not None:
            artwork = "data:image/jpeg;base64," + base64.b64encode(self.artwork_jpeg).decode()
        return MediaSession(
            id=self.id,
            app_id=self.app_id,
            app_name=self.app_name,
            title=self.title,
            artist=self.artist,
            album=self.album,
            artwork_id=self.artwork_id,
            artwork=artwork,
            status=self.status,
            position=self.position,
            duration=self.duration,
            rate=self.rate,
            can_seek=self.can_seek,
            can_next=self.can_next,
            can_prev=self.can_prev,
            updated_at=self.updated_at,
        )

    def with_artwork(self, jpeg: bytes | None) -> SessionSnapshot:
        return replace(self, artwork_jpeg=jpeg, artwork_id=artwork_id(jpeg))


def artwork_id(jpeg: bytes | None) -> str | None:
    """Short content hash: the same image always gets the same id."""
    if not jpeg:
        return None
    return hashlib.sha256(jpeg).hexdigest()[:16]


def thumbnail_jpeg(raw: bytes, max_px: int = ARTWORK_MAX_PX) -> bytes | None:
    """Decode any image the OS hands us and re-encode it as a JPEG of at most max_px."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.thumbnail((max_px, max_px))
            rgb = img.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=ARTWORK_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


# Known app ids (Windows AppUserModelIDs, macOS bundle ids, MPRIS names) -> friendly names.
_APP_NAMES: tuple[tuple[str, str], ...] = (
    ("spotify", "Spotify"),
    ("brave", "Brave"),
    ("msedge", "Edge"),
    ("microsoftedge", "Edge"),
    ("edge", "Edge"),
    ("chrome", "Chrome"),
    ("chromium", "Chromium"),
    ("firefox", "Firefox"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
    ("vlc", "VLC"),
    ("zunemusic", "Media Player"),
    ("zunevideo", "Movies & TV"),
    ("windows.media", "Media Player"),
    ("netflix", "Netflix"),
    ("primevideo", "Prime Video"),
    ("applemusic", "Apple Music"),
    ("com.apple.music", "Music"),
    ("com.apple.tv", "TV"),
    ("com.apple.safari", "Safari"),
    ("com.apple.quicktimeplayerx", "QuickTime Player"),
    ("iina", "IINA"),
    ("mpv", "mpv"),
    ("foobar2000", "foobar2000"),
    ("musicbee", "MusicBee"),
    ("itunes", "iTunes"),
    ("deezer", "Deezer"),
    ("tidal", "TIDAL"),
    ("youtube", "YouTube"),
)


def friendly_app_name(app_id: str) -> str:
    lowered = app_id.lower()
    for marker, name in _APP_NAMES:
        if marker in lowered:
            return name
    # Fall back to the last meaningful chunk, for example a path ending in "foo.exe" -> "Foo".
    chunk = re.split(r"[\\/!.]", app_id.removesuffix(".exe"))
    parts = [p for p in chunk if p and p.lower() not in ("exe", "app")]
    if not parts:
        return "Media"
    name = parts[-1].split("_")[0]
    return name[:1].upper() + name[1:] if name else "Media"


class MediaBackend(ABC):
    """One OS media-session source. Backends call ``_notify()`` whenever anything changes."""

    name: str = "base"

    def __init__(self) -> None:
        self._changed = asyncio.Event()

    def _notify(self) -> None:
        self._changed.set()

    async def changes(self) -> AsyncIterator[None]:
        """Yields once per burst of changes (bursts are coalesced)."""
        while True:
            await self._changed.wait()
            self._changed.clear()
            yield None

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def list_sessions(self) -> list[SessionSnapshot]: ...

    @abstractmethod
    def system_current_id(self) -> str | None:
        """The session the OS itself considers current, if it has that notion."""

    def current(self) -> SessionSnapshot | None:
        sessions = self.list_sessions()
        wanted = self.system_current_id()
        for session in sessions:
            if session.id == wanted:
                return session
        playing = [s for s in sessions if s.status == "playing"]
        if playing:
            return playing[0]
        return sessions[0] if sessions else None

    @abstractmethod
    async def command(self, session_id: str, action: MediaCommand) -> bool: ...

    @abstractmethod
    async def seek_to(self, session_id: str, seconds: float) -> bool: ...

    async def toggle(self, session_id: str) -> bool:
        return await self.command(session_id, "toggle")

    async def play(self, session_id: str) -> bool:
        return await self.command(session_id, "play")

    async def pause(self, session_id: str) -> bool:
        return await self.command(session_id, "pause")

    async def next(self, session_id: str) -> bool:
        return await self.command(session_id, "next")

    async def prev(self, session_id: str) -> bool:
        return await self.command(session_id, "prev")


class NoSessionBackend(MediaBackend):
    """Used when no session API is available: no sessions, so the key fallback handles commands."""

    name = "none"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def list_sessions(self) -> list[SessionSnapshot]:
        return []

    def system_current_id(self) -> str | None:
        return None

    async def command(self, session_id: str, action: MediaCommand) -> bool:
        return False

    async def seek_to(self, session_id: str, seconds: float) -> bool:
        return False
