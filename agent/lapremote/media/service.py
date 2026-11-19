"""Wires a media backend into the router and pushes media.state to every phone."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import shutil
from collections import OrderedDict
from collections.abc import Callable

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import (
    MediaBackend,
    MediaCommand,
    NoSessionBackend,
    SessionSnapshot,
    now_ms,
)
from lapremote.media.keys_fallback import MediaKeys
from lapremote.media.smart_seek import ApiSeek, KeySeek, SeekRefused, plan_seek
from lapremote.protocol import (
    MediaArtwork,
    MediaArtworkRequest,
    MediaSeek,
    MediaSelect,
    MediaState,
    MediaTarget,
    OsName,
)
from lapremote.router import ActionError
from lapremote.system.context import ForegroundInfo

log = get_logger("media")

ARTWORK_CACHE_SIZE = 64
# Re-send media.state for position changes only when they drift this far from interpolation.
POSITION_DRIFT_SECONDS = 1.0

NOTHING_PLAYING = "Nothing is playing right now."
PLAYER_GONE = "That player isn't open anymore."
NO_RESPONSE = "That player didn't respond."

ForegroundReader = Callable[[], ForegroundInfo | None]


def create_media_backend(os_name: OsName) -> tuple[MediaBackend, str | None]:
    """The backend for this OS and, when it is limited, a short setup hint."""
    if os_name == "windows":
        from lapremote.media.windows import WindowsMediaBackend  # noqa: PLC0415 - Windows only

        return WindowsMediaBackend(), None
    if os_name == "macos":
        from lapremote.media.macos import INSTALL_HELP, MacMediaBackend  # noqa: PLC0415

        exe = shutil.which("media-control")
        return (MacMediaBackend(exe), None) if exe else (NoSessionBackend(), INSTALL_HELP)
    from lapremote.media.linux import PlayerctlBackend  # noqa: PLC0415

    exe = shutil.which("playerctl")
    if exe:
        return PlayerctlBackend(exe), None
    return NoSessionBackend(), "For track info on Linux, install playerctl."


def _signature(s: SessionSnapshot) -> tuple[object, ...]:
    return (
        s.id,
        s.title,
        s.artist,
        s.album,
        s.status,
        s.duration,
        s.rate,
        s.can_seek,
        s.can_next,
        s.can_prev,
        s.artwork_id,
        s.position is None,
    )


class MediaService:
    def __init__(
        self,
        agent: Agent,
        backend: MediaBackend,
        keys: MediaKeys,
        foreground: ForegroundReader,
        setup_hint: str | None = None,
    ) -> None:
        self._agent = agent
        self._backend = backend
        self._keys = keys
        self._foreground = foreground
        self._setup_hint = setup_hint
        self._selected: str | None = None
        self._artwork: OrderedDict[str, bytes] = OrderedDict()
        self._sent: list[SessionSnapshot] = []
        self._watcher: asyncio.Task[None] | None = None

    @property
    def backend(self) -> MediaBackend:
        return self._backend

    def register(self) -> None:
        router = self._agent.router
        for action in ("toggle", "play", "pause", "next", "prev"):
            router.register(f"media.{action}", self._command_handler(action))  # type: ignore[arg-type]
        router.register("media.seek", self._seek)
        router.register("media.select", self._select)
        router.register("media.artwork", self._artwork_request)
        self._agent.on_connect.append(self._send_state)
        self._agent.on_startup.append(self.start)
        self._agent.on_shutdown.append(self.stop)
        self._agent.set_feature("media", True, self._setup_hint)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        try:
            await self._backend.start()
        except Exception as exc:  # the key fallback still works without a session API
            log_event(
                log, "media_backend_failed", level=40, backend=self._backend.name, error=repr(exc)
            )
            self._backend = NoSessionBackend()
            self._agent.set_feature("media", True, "Showing what's playing isn't available.")
        log_event(log, "media_ready", backend=self._backend.name)
        self._watcher = asyncio.get_running_loop().create_task(self._watch())

    async def stop(self) -> None:
        if self._watcher is not None:
            self._watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher
        await self._backend.stop()

    async def _watch(self) -> None:
        async for _ in self._backend.changes():
            await self.on_change()

    async def on_change(self) -> None:
        sessions = self._backend.list_sessions()
        for s in sessions:
            if s.artwork_id is not None and s.artwork_jpeg is not None:
                self._artwork[s.artwork_id] = s.artwork_jpeg
                self._artwork.move_to_end(s.artwork_id)
        while len(self._artwork) > ARTWORK_CACHE_SIZE:
            self._artwork.popitem(last=False)
        if self._changed(sessions):
            self._sent = sessions
            await self.broadcast()

    def _changed(self, sessions: list[SessionSnapshot]) -> bool:
        if [_signature(s) for s in sessions] != [_signature(s) for s in self._sent]:
            return True
        for new, old in zip(sessions, self._sent, strict=True):
            if new.position is None or old.position is None:
                continue
            predicted = old.position_now(new.updated_at)
            if predicted is not None and abs(predicted - new.position) > POSITION_DRIFT_SECONDS:
                return True
        return False

    # ------------------------------------------------------------------ state

    def current_id(self) -> str | None:
        sessions = self._backend.list_sessions()
        if self._selected is not None and any(s.id == self._selected for s in sessions):
            return self._selected
        current = self._backend.current()
        return current.id if current is not None else None

    def state_for(self, conn: Connection) -> MediaState:
        wire = []
        for s in self._backend.list_sessions():
            include = s.artwork_id is not None and s.artwork_id not in conn.sent_artwork
            wire.append(s.to_wire(include_artwork=include))
            if include and s.artwork_id is not None:
                conn.sent_artwork.add(s.artwork_id)
        return MediaState(sessions=wire, current_id=self.current_id(), ts=now_ms())

    async def broadcast(self) -> None:
        for conn in self._agent.hub.authed():
            await conn.send("media.state", self.state_for(conn))

    async def _send_state(self, conn: Connection) -> None:
        await conn.send("media.state", self.state_for(conn))

    def _target(self, session_id: str | None) -> SessionSnapshot | None:
        sessions = self._backend.list_sessions()
        if session_id is not None:
            found = next((s for s in sessions if s.id == session_id), None)
            if found is None:
                raise ActionError(PLAYER_GONE)
            return found
        wanted = self.current_id()
        return next((s for s in sessions if s.id == wanted), None)

    # ------------------------------------------------------------------ handlers

    def _command_handler(self, action: MediaCommand) -> Callable[[Connection, MediaTarget], object]:
        async def handler(_conn: Connection, p: MediaTarget) -> None:
            await self.command(action, p.session_id)

        return handler

    async def command(self, action: MediaCommand, session_id: str | None = None) -> None:
        session = self._target(session_id)
        if session is None:
            # No session API or nothing listed: the OS media keys reach whatever is playing.
            if self._keys.command(action):
                return
            raise ActionError(NOTHING_PLAYING)
        if await self._backend.command(session.id, action):
            return
        is_system_current = session.id == self._backend.system_current_id()
        if is_system_current and self._keys.command(action):
            return
        raise ActionError(NO_RESPONSE)

    async def _seek(self, _conn: Connection, p: MediaSeek) -> None:
        await self.seek(p.session_id, to=p.to, by=p.by)

    async def seek(self, session_id: str | None, *, to: float | None, by: float | None) -> None:
        session = self._target(session_id)
        foreground = None
        if session is None or not session.can_seek:
            foreground = await asyncio.to_thread(self._foreground)
        plan = plan_seek(session, to=to, by=by, foreground=foreground)
        if isinstance(plan, SeekRefused):
            raise ActionError(plan.reason)
        if isinstance(plan, ApiSeek):
            if session is None or not await self._backend.seek_to(session.id, plan.seconds):
                raise ActionError("That player didn't accept the seek.")
            return
        if isinstance(plan, KeySeek) and not self._keys.press(plan.key, plan.presses):
            raise ActionError("Keyboard control isn't available on this laptop.")

    async def select(self, session_id: str) -> None:
        if not any(s.id == session_id for s in self._backend.list_sessions()):
            raise ActionError(PLAYER_GONE)
        self._selected = session_id
        await self.broadcast()

    async def _select(self, _conn: Connection, p: MediaSelect) -> None:
        await self.select(p.session_id)

    async def _artwork_request(self, conn: Connection, p: MediaArtworkRequest) -> None:
        jpeg = self._artwork.get(p.artwork_id)
        data = None
        if jpeg is not None:
            data = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
            conn.sent_artwork.add(p.artwork_id)
        await conn.send("media.artwork", MediaArtwork(artwork_id=p.artwork_id, artwork=data))
