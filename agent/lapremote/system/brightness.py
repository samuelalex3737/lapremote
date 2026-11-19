"""Screen brightness through screen-brightness-control (Windows and Linux).

macOS is reported as unsupported: there is no public, permission-free API for the
built-in display that works across Mac models.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import BrightnessSet, BrightnessState, OsName
from lapremote.router import ActionError

log = get_logger("brightness")

POLL_SECONDS = 5.0
MAC_REASON = "Brightness control isn't supported on macOS."


class BrightnessError(Exception):
    """The brightness could not be read or changed."""


class BrightnessBackend(Protocol):
    def get(self) -> int: ...
    def set(self, level: int) -> None: ...


class SbcBackend:
    """The first display reported by screen-brightness-control (the built-in panel on laptops)."""

    def get(self) -> int:
        import screen_brightness_control as sbc  # noqa: PLC0415 - optional per OS

        try:
            values = sbc.get_brightness(display=0)
        except Exception as exc:  # the library raises its own exception types per method
            raise BrightnessError(str(exc)) from exc
        if not values:
            msg = "no display reported a brightness"
            raise BrightnessError(msg)
        return int(values[0])

    def set(self, level: int) -> None:
        import screen_brightness_control as sbc  # noqa: PLC0415

        try:
            sbc.set_brightness(level, display=0)
        except Exception as exc:
            raise BrightnessError(str(exc)) from exc


def create_brightness_backend(os_name: OsName) -> tuple[BrightnessBackend | None, str | None]:
    if os_name == "macos":
        return None, MAC_REASON
    backend = SbcBackend()
    try:
        backend.get()
    except (BrightnessError, ImportError) as exc:
        log_event(log, "brightness_unavailable", level=30, error=str(exc))
        return None, "This laptop's screen doesn't allow brightness control."
    return backend, None


class BrightnessService:
    def __init__(
        self, agent: Agent, backend: BrightnessBackend | None, reason: str | None = None
    ) -> None:
        self._agent = agent
        self._backend = backend
        self._reason = reason
        self._level: int | None = None
        self._task: asyncio.Task[None] | None = None

    def register(self) -> None:
        self._agent.on_connect.append(self._send)
        if self._backend is None:
            self._agent.set_feature("brightness", False, self._reason)
            return
        self._agent.set_feature("brightness", True)
        self._agent.router.register("brightness.set", self._set)
        self._agent.on_startup.append(self.start)
        self._agent.on_shutdown.append(self.stop)

    def state(self) -> BrightnessState:
        return BrightnessState(level=self._level, supported=self._backend is not None)

    async def start(self) -> None:
        await self.refresh(broadcast=False)
        self._task = asyncio.get_running_loop().create_task(self._poll())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            await self.refresh()

    async def refresh(self, *, broadcast: bool = True) -> None:
        backend = self._backend
        if backend is None:
            return
        try:
            level = await asyncio.to_thread(backend.get)
        except BrightnessError:
            return
        if level != self._level:
            self._level = level
            if broadcast:
                await self._agent.hub.broadcast("brightness.state", self.state())

    async def set_level(self, level: int) -> None:
        backend = self._backend
        if backend is None:
            raise ActionError(self._reason or "Brightness control isn't available.")
        try:
            await asyncio.to_thread(backend.set, max(0, min(100, level)))
        except BrightnessError as exc:
            raise ActionError("Couldn't change the brightness.") from exc
        await self.refresh()

    async def _set(self, _conn: Connection, p: BrightnessSet) -> None:
        await self.set_level(p.level)

    async def _send(self, conn: Connection) -> None:
        await conn.send("brightness.state", self.state())
