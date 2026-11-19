"""Scenes: named step lists (volume, brightness, launch, play/pause, wait) run in order.

Scenes live in ~/.lapremote/scenes.json, seeded from shared/scenes.default.json.
A scene runs in the background; the phone gets an ack when it starts and a toast
when it finishes (naming any step that failed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from lapremote.actions import Actions
from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    BrightnessSetStep,
    LaunchOpenStep,
    MediaPauseStep,
    MediaPlayStep,
    Scene,
    SceneRun,
    ScenesDelete,
    ScenesSave,
    ScenesState,
    SceneStep,
    Toast,
    VolumeSetStep,
    WaitStep,
)
from lapremote.router import ActionError
from lapremote.storage import load_or_seed, write_json_atomic

log = get_logger("scenes")

MAX_SCENES = 40
_LIST = TypeAdapter(list[Scene])

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class StepResult:
    type: str
    ok: bool
    error: str | None = None


async def run_steps(
    steps: list[SceneStep], actions: Actions, sleep: Sleep = asyncio.sleep
) -> list[StepResult]:
    """Run every step in order. A failed step is recorded and the scene carries on."""
    results: list[StepResult] = []
    for step in steps:
        try:
            if isinstance(step, VolumeSetStep):
                await actions.volume_set(step.level)
            elif isinstance(step, BrightnessSetStep):
                await actions.brightness_set(step.level)
            elif isinstance(step, LaunchOpenStep):
                await actions.launch(step.shortcut_id)
            elif isinstance(step, MediaPlayStep):
                await actions.media_command("play")
            elif isinstance(step, MediaPauseStep):
                await actions.pause_all()
            elif isinstance(step, WaitStep):
                await sleep(step.ms / 1000)
        except ActionError as exc:
            results.append(StepResult(step.type, False, exc.message))
            continue
        results.append(StepResult(step.type, True))
    return results


class SceneStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        try:
            self._items = _LIST.validate_python(load_or_seed(path, "scenes.default.json"))
        except ValidationError:
            path.replace(path.with_suffix(".json.broken"))
            self._items = _LIST.validate_python(load_or_seed(path, "scenes.default.json"))

    def items(self) -> list[Scene]:
        return list(self._items)

    def get(self, scene_id: str) -> Scene | None:
        return next((s for s in self._items if s.id == scene_id), None)

    def _save(self) -> None:
        write_json_atomic(
            self._path, [s.model_dump(mode="json", by_alias=True) for s in self._items]
        )

    def upsert(self, scene: Scene) -> None:
        for i, existing in enumerate(self._items):
            if existing.id == scene.id:
                self._items[i] = scene
                self._save()
                return
        if len(self._items) >= MAX_SCENES:
            msg = "too many scenes"
            raise OverflowError(msg)
        self._items.append(scene)
        self._save()

    def delete(self, scene_id: str) -> bool:
        before = len(self._items)
        self._items = [s for s in self._items if s.id != scene_id]
        if len(self._items) != before:
            self._save()
            return True
        return False


class SceneService:
    def __init__(
        self, agent: Agent, store: SceneStore, actions: Actions, sleep: Sleep = asyncio.sleep
    ) -> None:
        self._agent = agent
        self._store = store
        self._actions = actions
        self._sleep = sleep

    def register(self) -> None:
        self._agent.set_feature("scenes", True)
        router = self._agent.router
        router.register("scene.run", self._run)
        router.register("scenes.save", self._save)
        router.register("scenes.delete", self._delete)
        self._agent.on_connect.append(self._send_state)

    def state(self) -> ScenesState:
        return ScenesState(scenes=self._store.items())

    async def _send_state(self, conn: Connection) -> None:
        await conn.send("scenes.state", self.state())

    async def run(self, scene_id: str) -> list[StepResult]:
        scene = self._store.get(scene_id)
        if scene is None:
            raise ActionError("That scene doesn't exist anymore.")
        results = await run_steps(scene.steps, self._actions, self._sleep)
        failed = [r for r in results if not r.ok]
        log_event(log, "scene_ran", scene=scene.id, steps=len(results), failed=len(failed))
        return results

    async def _run(self, conn: Connection, p: SceneRun) -> None:
        scene = self._store.get(p.scene_id)
        if scene is None:
            raise ActionError("That scene doesn't exist anymore.")

        async def go() -> None:
            results = await self.run(p.scene_id)
            failed = [r for r in results if not r.ok]
            if failed:
                first = failed[0]
                message = f"{scene.name} finished, but one step didn't work: {first.error}"
                await conn.send("toast", Toast(level="warn", message=message[:300]))
            else:
                await conn.send("toast", Toast(level="success", message=f"{scene.name} is on."))

        # Scenes can wait for minutes, so they run beside the phone's other messages.
        self._agent.spawn(go())

    async def _save(self, _conn: Connection, p: ScenesSave) -> None:
        try:
            self._store.upsert(p.scene)
        except OverflowError as exc:
            raise ActionError(f"You can have up to {MAX_SCENES} scenes.") from exc
        await self._agent.hub.broadcast("scenes.state", self.state())

    async def _delete(self, _conn: Connection, p: ScenesDelete) -> None:
        if not self._store.delete(p.scene_id):
            raise ActionError("That scene doesn't exist anymore.")
        await self._agent.hub.broadcast("scenes.state", self.state())
