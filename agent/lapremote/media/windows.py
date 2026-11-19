"""Windows media sessions through GlobalSystemMediaTransportControlsSessionManager (GSMTC)."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
from lapremote.protocol import MediaStatus

log = get_logger("media.windows")

# GlobalSystemMediaTransportControlsSessionPlaybackStatus
_PLAYING = 4
_PAUSED = 5
_TICKS_PER_SECOND = 10_000_000
_DEBOUNCE_SECONDS = 0.05


def _status(value: int) -> MediaStatus:
    if value == _PLAYING:
        return "playing"
    if value == _PAUSED:
        return "paused"
    return "stopped"


def _seconds(value: timedelta | None) -> float:
    return value.total_seconds() if value is not None else 0.0


def _epoch_ms(value: datetime | None) -> float:
    if value is None or value.year < 2000:
        return now_ms()
    return value.timestamp() * 1000


@dataclass
class _Tracked:
    wrapper: Any
    id: str
    tokens: list[tuple[str, Any]] = field(default_factory=list)
    art_key: tuple[str, str, str] | None = None
    art_jpeg: bytes | None = None
    snapshot: SessionSnapshot | None = None


class WindowsMediaBackend(MediaBackend):
    name = "gsmtc"

    def __init__(self) -> None:
        super().__init__()
        self._manager: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tracked: list[_Tracked] = []
        self._ids = itertools.count(1)
        self._manager_tokens: list[tuple[str, Any]] = []
        self._refresh_task: asyncio.Task[None] | None = None
        self._pending = False
        self._current_aumid: str | None = None

    async def start(self) -> None:
        from winrt.windows.media.control import (  # noqa: PLC0415 - Windows only
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )

        self._loop = asyncio.get_running_loop()
        self._manager = await Manager.request_async()
        self._manager_tokens = [
            ("sessions_changed", self._manager.add_sessions_changed(self._on_event)),
            ("current_session_changed", self._manager.add_current_session_changed(self._on_event)),
        ]
        await self._refresh()

    async def stop(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
        for tracked in self._tracked:
            self._unsubscribe(tracked)
        self._tracked = []
        if self._manager is not None:
            for name, token in self._manager_tokens:
                getattr(self._manager, f"remove_{name}")(token)
        self._manager = None

    # WinRT raises events on its own threads: hop back onto the event loop.
    def _on_event(self, _sender: object, _args: object) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._schedule_refresh)

    def _schedule_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._pending = True
            return
        self._refresh_task = asyncio.get_running_loop().create_task(self._debounced_refresh())

    async def _debounced_refresh(self) -> None:
        while True:
            self._pending = False
            await asyncio.sleep(_DEBOUNCE_SECONDS)
            try:
                await self._refresh()
            except OSError as exc:
                log_event(log, "refresh_failed", level=30, error=str(exc))
            if not self._pending:
                return

    def _subscribe(self, tracked: _Tracked) -> None:
        session = tracked.wrapper
        tracked.tokens = [
            ("media_properties_changed", session.add_media_properties_changed(self._on_event)),
            ("playback_info_changed", session.add_playback_info_changed(self._on_event)),
            (
                "timeline_properties_changed",
                session.add_timeline_properties_changed(self._on_event),
            ),
        ]

    def _unsubscribe(self, tracked: _Tracked) -> None:
        for name, token in tracked.tokens:
            with contextlib.suppress(OSError):
                getattr(tracked.wrapper, f"remove_{name}")(token)
        tracked.tokens = []

    async def _refresh(self) -> None:
        manager = self._manager
        if manager is None:
            return
        wrappers = list(manager.get_sessions())
        current = manager.get_current_session()
        self._current_aumid = current.source_app_user_model_id if current is not None else None

        # Wrappers compare equal when they wrap the same session, so ids stay stable.
        kept: list[_Tracked] = []
        for wrapper in wrappers:
            found = next((t for t in self._tracked if t.wrapper == wrapper), None)
            if found is None:
                found = _Tracked(wrapper=wrapper, id=f"w{next(self._ids)}")
                self._subscribe(found)
            kept.append(found)
        for gone in self._tracked:
            if gone not in kept:
                self._unsubscribe(gone)
        self._tracked = kept

        for tracked in kept:
            try:
                tracked.snapshot = await self._snapshot(tracked)
            except OSError as exc:
                log_event(log, "session_read_failed", level=30, session=tracked.id, error=str(exc))
        self._notify()

    async def _snapshot(self, tracked: _Tracked) -> SessionSnapshot:
        session = tracked.wrapper
        aumid: str = session.source_app_user_model_id or "unknown"
        props = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()
        controls = playback.controls

        title = (props.title or "") if props is not None else ""
        artist = (props.artist or "") if props is not None else ""
        album = (props.album_title or "") if props is not None else ""
        key = (title, artist, album)
        if props is not None and key != tracked.art_key:
            tracked.art_key = key
            tracked.art_jpeg = await self._read_thumbnail(props.thumbnail)

        start = _seconds(timeline.start_time)
        end = _seconds(timeline.end_time)
        has_timeline = end > start
        status = _status(int(playback.playback_status))
        rate = float(playback.playback_rate) if playback.playback_rate else 1.0
        snapshot = SessionSnapshot(
            id=tracked.id,
            app_id=aumid,
            app_name=friendly_app_name(aumid),
            title=title,
            artist=artist,
            album=album,
            status=status,
            position=_seconds(timeline.position) - start if has_timeline else None,
            duration=end - start if has_timeline else None,
            rate=rate,
            can_seek=bool(controls.is_playback_position_enabled) and has_timeline,
            can_next=bool(controls.is_next_enabled),
            can_prev=bool(controls.is_previous_enabled),
            updated_at=_epoch_ms(timeline.last_updated_time),
        )
        return snapshot.with_artwork(tracked.art_jpeg)

    @staticmethod
    async def _read_thumbnail(reference: Any) -> bytes | None:
        if reference is None:
            return None
        from winrt.windows.storage.streams import (  # noqa: PLC0415 - Windows only
            Buffer,
            InputStreamOptions,
        )

        try:
            stream = await reference.open_read_async()
            size = int(stream.size)
            if size <= 0 or size > 8_000_000:
                return None
            result = await stream.read_async(Buffer(size), size, InputStreamOptions.READ_AHEAD)
            raw = bytes(result)
        except OSError:
            return None
        return await asyncio.to_thread(thumbnail_jpeg, raw)

    def list_sessions(self) -> list[SessionSnapshot]:
        return [t.snapshot for t in self._tracked if t.snapshot is not None]

    def system_current_id(self) -> str | None:
        for tracked in self._tracked:
            if tracked.snapshot is not None and tracked.snapshot.app_id == self._current_aumid:
                return tracked.id
        return None

    def _wrapper(self, session_id: str) -> Any:
        for tracked in self._tracked:
            if tracked.id == session_id:
                return tracked.wrapper
        return None

    async def command(self, session_id: str, action: MediaCommand) -> bool:
        session = self._wrapper(session_id)
        if session is None:
            return False
        method = {
            "toggle": session.try_toggle_play_pause_async,
            "play": session.try_play_async,
            "pause": session.try_pause_async,
            "next": session.try_skip_next_async,
            "prev": session.try_skip_previous_async,
        }[action]
        try:
            return bool(await method())
        except OSError:
            return False

    async def seek_to(self, session_id: str, seconds: float) -> bool:
        session = self._wrapper(session_id)
        if session is None:
            return False
        timeline = session.get_timeline_properties()
        target = _seconds(timeline.start_time) + max(0.0, seconds)
        try:
            return bool(
                await session.try_change_playback_position_async(int(target * _TICKS_PER_SECOND))
            )
        except OSError:
            return False
