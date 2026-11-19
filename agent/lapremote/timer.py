"""Sleep timer: after N minutes (or at the end of the current track/episode) pause
everything, optionally lock or sleep the laptop.

Over the last 30 seconds the volume fades to zero; after pausing, the original
level is restored so the next thing you play isn't silent.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

from lapremote.actions import Actions
from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import SessionSnapshot
from lapremote.protocol import Empty, TimerMode, TimerSet, TimerState, TimerThen, Toast
from lapremote.router import ActionError

log = get_logger("timer")

FADE_SECONDS = 30.0
NO_DURATION = "This track doesn't say how long it is, so the timer can't wait for its end."
NOTHING_PLAYING = "Nothing is playing, so there is no end to wait for."

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


def seconds_until_end(session: SessionSnapshot | None, now_ms: float) -> float:
    """Remaining time of the current media, or ActionError when it can't be known."""
    if session is None:
        raise ActionError(NOTHING_PLAYING)
    position = session.position_now(now_ms)
    if session.duration is None or position is None or session.duration <= 0:
        raise ActionError(NO_DURATION)
    return max(0.0, (session.duration - position) / max(session.rate, 0.01))


def fade_levels(start: int, seconds: float) -> list[int]:
    """Volume level for each second of the fade, ending at 0."""
    steps = max(1, int(seconds))
    return [round(start * (steps - i) / steps) for i in range(1, steps + 1)]


class SleepTimer:
    def __init__(
        self,
        agent: Agent,
        actions: Actions,
        *,
        fade_seconds: float = FADE_SECONDS,
        wall: Clock = time.time,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._agent = agent
        self._actions = actions
        self._fade = fade_seconds
        self._wall = wall
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._ends_at: float | None = None
        self._mode: TimerMode | None = None
        self._then: TimerThen | None = None
        self._restore: int | None = None

    def register(self) -> None:
        self._agent.set_feature("timer", True)
        self._agent.router.register("timer.set", self._set)
        self._agent.router.register("timer.cancel", self._cancel)
        self._agent.on_connect.append(self._send)
        self._agent.on_shutdown.append(self.cancel)

    def state(self) -> TimerState:
        active = self._task is not None and not self._task.done()
        return TimerState(
            active=active,
            ends_at=self._ends_at if active else None,
            mode=self._mode if active else None,
            then=self._then if active else None,
        )

    async def _broadcast(self) -> None:
        await self._agent.hub.broadcast("timer.state", self.state())

    async def _send(self, conn: Connection) -> None:
        await conn.send("timer.state", self.state())

    async def start(self, mode: TimerMode, then: TimerThen, minutes: float | None) -> TimerState:
        now_ms = self._wall() * 1000
        if mode == "end_of_media":
            delay = seconds_until_end(self._actions.media.backend.current(), now_ms)
        else:
            if minutes is None:
                raise ActionError("Pick how many minutes.")
            delay = minutes * 60
        await self.cancel(broadcast=False)
        self._ends_at = now_ms + delay * 1000
        self._mode = mode
        self._then = then
        self._task = asyncio.get_running_loop().create_task(self._run(delay))
        log_event(log, "timer_set", mode=mode, then=then, seconds=round(delay, 1))
        await self._broadcast()
        return self.state()

    async def cancel(self, *, broadcast: bool = True) -> None:
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._restore_volume()
        if broadcast:
            await self._broadcast()

    async def _restore_volume(self) -> None:
        level = self._restore
        self._restore = None
        if level is not None:
            with contextlib.suppress(ActionError):
                await self._actions.volume_set(level)

    async def _run(self, delay: float) -> None:
        fade = min(self._fade, delay)
        await self._sleep(max(0.0, delay - fade))
        start = self._actions.volume_level()
        if start is not None and start > 0 and fade >= 1:
            self._restore = start
            for level in fade_levels(start, fade):
                with contextlib.suppress(ActionError):
                    await self._actions.volume_set(level)
                await self._sleep(1.0)
        elif fade > 0:
            await self._sleep(fade)
        paused = await self._actions.pause_all()
        await self._restore_volume()
        then = self._then
        log_event(log, "timer_fired", paused=paused, then=then)
        self._task = None
        await self._broadcast()
        message = "Sleep timer: paused." if paused else "Sleep timer finished."
        await self._agent.hub.broadcast("toast", Toast(level="info", message=message))
        if then == "pause_lock":
            await self._actions.power_run("lock")
        elif then == "pause_sleep":
            await self._actions.power_run("sleep")

    async def _set(self, _conn: Connection, p: TimerSet) -> None:
        await self.start(p.mode, p.then, p.minutes)

    async def _cancel(self, _conn: Connection, _p: Empty) -> None:
        await self.cancel()
