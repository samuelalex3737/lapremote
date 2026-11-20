"""ai.command and ai.confirm: plan with the model, then run the validated actions in order."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lapremote.ai.planner import PlanDraft, Planner, PlannerContext
from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.media.base import MediaCommand
from lapremote.media.service import NOTHING_PLAYING
from lapremote.protocol import AiAction, AiCommand, AiConfirm, AiPlan, AiResult, AiStepResult
from lapremote.router import ActionError

if TYPE_CHECKING:
    from lapremote.services import Services
    from lapremote.system.context import ContextService

log = get_logger("ai")

PLAN_TTL_SECONDS = 60.0
CHECK_INTERVAL_SECONDS = 30.0
MEDIA_COMMANDS: dict[str, MediaCommand] = {
    "media.toggle": "toggle",
    "media.play": "play",
    "media.next": "next",
    "media.prev": "prev",
}

Sleep = Callable[[float], Awaitable[None]]


@dataclass
class _Pending:
    device_id: str | None
    actions: list[AiAction]
    expires: float


class ActionRunner:
    """Runs one validated AI action through the same services the phone uses."""

    def __init__(self, services: Services, sleep: Sleep = asyncio.sleep) -> None:
        self._s = services
        self.sleep = sleep

    async def run(self, action: AiAction) -> None:  # noqa: PLR0912 - a branch per action type
        s = self._s
        p = action.payload
        t = action.type
        if t in MEDIA_COMMANDS:
            await s.media.command(MEDIA_COMMANDS[t], p.get("sessionId"))
        elif t == "media.pause":
            if p.get("sessionId") is not None:
                await s.media.command("pause", p["sessionId"])
            elif await s.actions.pause_all() == 0:
                raise ActionError(NOTHING_PLAYING)
        elif t == "media.seek":
            await s.media.seek(p.get("sessionId"), to=p.get("to"), by=p.get("by"))
        elif t == "media.select":
            await s.media.select(p["sessionId"])
        elif t == "volume.set":
            await s.volume.set_level(p["level"], show=True)
        elif t == "volume.step":
            await s.volume.step(p["delta"])
        elif t == "volume.mute":
            await s.volume.set_muted(p["muted"])
        elif t == "brightness.set":
            await s.brightness.set_level(p["level"])
        elif t == "power.action":
            await s.power.run(p["action"])
        elif t == "launch.open":
            await s.shortcuts.launch(p["shortcutId"])
        elif t == "scene.run":
            failed = [r for r in await s.scenes.run(p["sceneId"]) if not r.ok]
            if failed:
                raise ActionError(failed[0].error or "A scene step didn't work.")
        elif t == "timer.set":
            await s.timer.start(p["mode"], p["then"], p.get("minutes"))
        elif t == "timer.cancel":
            await s.timer.cancel()
        elif t == "key.press":
            await s.input.press_key(p["key"], p.get("modifiers", []))
        elif t == "key.text":
            await s.input.type_text(p["text"])
        elif t == "wait":
            await self.sleep(p["ms"] / 1000)
        else:
            raise ActionError("That action isn't allowed.")


def build_context(services: Services, context: ContextService | None) -> PlannerContext:
    sessions = services.media.backend.list_sessions()
    volume = services.volume.state
    timer = services.timer.state()
    fg = context.current if context is not None else None
    return PlannerContext(
        media=[
            {
                "id": s.id,
                "app": s.app_name,
                "title": s.title,
                "artist": s.artist,
                "status": s.status,
                "position": round(p) if (p := s.position_now()) is not None else None,
                "duration": round(s.duration) if s.duration is not None else None,
                "canSeek": s.can_seek,
            }
            for s in sessions
        ],
        current_media_id=services.media.current_id(),
        # The window title is left out on purpose: it can hold private text.
        foreground=(
            {"app": fg.app, "category": fg.category, "site": fg.site} if fg is not None else None
        ),
        volume={"level": volume[0], "muted": volume[1]} if volume is not None else None,
        brightness=services.brightness.state().level,
        timer=({"endsAt": timer.ends_at, "then": timer.then} if timer.active else None),
        shortcuts=[
            {"id": sc.id, "name": sc.name, "kind": sc.kind}
            for sc in services.shortcuts.store.items()
            if sc.id != "_once"
        ],
        scenes=[{"id": sc.id, "name": sc.name} for sc in services.scenes.state().scenes],
    )


class AiService:
    def __init__(
        self,
        agent: Agent,
        services: Services,
        planner: Planner,
        context: ContextService | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._agent = agent
        self._services = services
        self._planner = planner
        self._context = context
        self._clock = clock
        self.runner = ActionRunner(services, sleep)
        self._pending: dict[str, _Pending] = {}
        self._checker: asyncio.Task[None] | None = None

    def register(self) -> None:
        router = self._agent.router
        # Planning can take several seconds, so it must not hold up trackpad messages.
        router.register("ai.command", self._command, background=True)
        router.register("ai.confirm", self._confirm)
        self._agent.set_feature("ai", False, "Checking the AI model...")
        self._agent.on_startup.append(self.start)
        self._agent.on_shutdown.append(self.stop)

    async def start(self) -> None:
        await self.check()
        self._checker = asyncio.get_running_loop().create_task(self._keep_checking())

    async def stop(self) -> None:
        if self._checker is not None:
            self._checker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._checker

    async def _keep_checking(self) -> None:
        while True:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await self.check()

    async def check(self) -> None:
        provider = self._planner.provider
        reason = await provider.check()
        previous = self._agent.feature_status["ai"]
        self._agent.set_feature("ai", reason is None, reason)
        if previous.available != (reason is None) or previous.reason != reason:
            log_event(
                log, "ai_status", provider=provider.name, model=provider.model, ready=reason is None
            )

    # ------------------------------------------------------------------ handlers

    async def plan(self, conn: Connection, text: str) -> tuple[str, PlanDraft]:
        context = build_context(self._services, self._context)
        started = time.perf_counter()
        draft = await self._planner.plan(text, context)
        # Never log the request or the reply: they are the person's own words.
        log_event(
            log,
            "ai_planned",
            device=conn.device_id,
            actions=[a.type for a in draft.actions],
            dropped=len(draft.dropped),
            confirm=draft.needs_confirm,
            ms=round((time.perf_counter() - started) * 1000),
        )
        return secrets.token_urlsafe(9), draft

    async def _command(self, conn: Connection, p: AiCommand) -> None:
        plan_id, draft = await self.plan(conn, p.text)
        await conn.send(
            "ai.plan",
            AiPlan(
                plan_id=plan_id,
                reply=draft.reply,
                actions=draft.actions,
                needs_confirm=draft.needs_confirm,
            ),
        )
        if not draft.actions:
            return
        if draft.needs_confirm:
            now = self._clock()
            self._pending = {k: v for k, v in self._pending.items() if v.expires > now}
            self._pending[plan_id] = _Pending(conn.device_id, draft.actions, now + PLAN_TTL_SECONDS)
            return
        await self.execute(conn, plan_id, draft.actions)

    async def _confirm(self, conn: Connection, p: AiConfirm) -> None:
        pending = self._pending.get(p.plan_id)
        if pending is None or pending.device_id != conn.device_id:
            raise ActionError("That plan isn't waiting anymore. Ask again.")
        del self._pending[p.plan_id]
        if pending.expires <= self._clock():
            raise ActionError("That plan expired. Ask again.")
        log_event(log, "ai_confirmed", device=conn.device_id, approve=p.approve)
        if p.approve:
            # Waits inside a plan can take a while; the ack goes out right away.
            self._agent.spawn(self._execute_quietly(conn, p.plan_id, pending.actions))

    async def _execute_quietly(
        self, conn: Connection, plan_id: str, actions: list[AiAction]
    ) -> None:
        await self.execute(conn, plan_id, actions)

    async def execute(self, conn: Connection, plan_id: str, actions: list[AiAction]) -> AiResult:
        steps: list[AiStepResult] = []
        for action in actions:
            try:
                await self.runner.run(action)
            except ActionError as exc:
                steps.append(AiStepResult(type=action.type, ok=False, error=exc.message))
                continue
            except Exception:
                log.exception("ai_step_crashed", extra={"fields": {"type": action.type}})
                steps.append(
                    AiStepResult(type=action.type, ok=False, error="Something went wrong.")
                )
                continue
            steps.append(AiStepResult(type=action.type, ok=True))
        result = AiResult(plan_id=plan_id, steps=steps)
        log_event(
            log,
            "ai_ran",
            device=conn.device_id,
            ok=sum(s.ok for s in steps),
            failed=sum(not s.ok for s in steps),
        )
        await conn.send("ai.result", result)
        return result
