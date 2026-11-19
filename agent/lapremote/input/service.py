"""Wires the mouse and keyboard into the router: input.* and key.* handlers."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from lapremote.connection import Connection
from lapremote.core import Agent
from lapremote.input.keyboard import Keyboard, PynputKeyboard, UnsupportedKeyError
from lapremote.input.mouse import Mouse, PynputMouse
from lapremote.logging_setup import get_logger, log_event
from lapremote.protocol import (
    Button,
    InputButton,
    InputMove,
    InputScroll,
    InputZoom,
    KeyPress,
    KeyText,
    OsName,
    Toast,
)
from lapremote.router import ActionError
from lapremote.system.permissions import (
    InputPermission,
    input_permission,
    mac_accessibility_trusted,
)
from lapremote.system.platform_info import DisplayServer

log = get_logger("input")


@dataclass
class InputDevices:
    mouse: Mouse | None
    keyboard: Keyboard | None
    permission: InputPermission


@dataclass
class DryRunBackend:
    """Records what would have been sent instead of moving the real cursor (``--input-dry-run``)."""

    calls: Counter[str] = field(default_factory=Counter)

    def _record(self, action: str, **fields: Any) -> None:
        self.calls[action] += 1
        log_event(log, "dry_run_input", action=action, **fields)

    def move(self, dx: int, dy: int) -> None:
        self._record("move", dx=dx, dy=dy)

    def press(self, key: object) -> None:
        self._record("press", key=str(key))

    def release(self, key: object) -> None:
        self._record("release", key=str(key))

    def scroll(self, dx: float, dy: float) -> None:
        self._record("scroll", dx=round(dx, 4), dy=round(dy, 4))

    def resolve(self, name: str) -> object:
        return name

    def type(self, text: str) -> None:
        # Typed text is never logged, only its length.
        self._record("type", textLength=len(text))


def detect_input_devices(
    os_name: OsName, display_server: DisplayServer | None, *, dry_run: bool = False
) -> InputDevices:
    if dry_run:
        backend = DryRunBackend()
        return InputDevices(
            Mouse(backend, os_name), Keyboard(backend, os_name), InputPermission(True, None)
        )
    permission = input_permission(os_name, display_server, mac_accessibility_trusted())
    if not permission.available:
        return InputDevices(None, None, permission)
    try:
        mouse = Mouse(PynputMouse(), os_name)
        keyboard = Keyboard(PynputKeyboard(), os_name)
    except Exception as exc:  # any backend failure means "input unavailable"
        log_event(log, "input_backend_failed", level=40, error=repr(exc))
        return InputDevices(
            None, None, InputPermission(False, "Couldn't start mouse and keyboard control.")
        )
    return InputDevices(mouse, keyboard, permission)


class InputService:
    def __init__(self, agent: Agent, devices: InputDevices) -> None:
        self._agent = agent
        self._devices = devices
        # Buttons each connection is holding, so a dropped phone never leaves a button stuck.
        self._held: dict[str, set[Button]] = {}

    def register(self) -> None:
        permission = self._devices.permission
        mouse, keyboard = self._devices.mouse, self._devices.keyboard
        if not permission.available or mouse is None or keyboard is None:
            self._agent.set_feature("input", False, permission.reason)
            self._agent.on_connect.append(self._warn_unavailable)
            log_event(log, "input_unavailable", reason=permission.reason)
            return
        self._agent.set_feature("input", True)
        router = self._agent.router
        router.register("input.move", self._move)
        router.register("input.click", self._click)
        router.register("input.down", self._down)
        router.register("input.up", self._up)
        router.register("input.scroll", self._scroll)
        router.register("input.zoom", self._zoom)
        router.register("key.press", self._key_press)
        router.register("key.text", self._key_text)
        self._agent.on_disconnect.append(self._release_for)

    @property
    def _mouse(self) -> Mouse:
        mouse = self._devices.mouse
        if mouse is None:
            raise ActionError("Mouse control isn't available on this laptop.")
        return mouse

    @property
    def _keyboard(self) -> Keyboard:
        keyboard = self._devices.keyboard
        if keyboard is None:
            raise ActionError("Keyboard control isn't available on this laptop.")
        return keyboard

    async def _warn_unavailable(self, conn: Connection) -> None:
        reason = self._devices.permission.reason
        if reason and conn.role == "owner":
            await conn.send("toast", Toast(level="warn", message=reason[:300]))

    async def _move(self, _conn: Connection, p: InputMove) -> None:
        self._mouse.move(p.dx, p.dy)

    async def _click(self, conn: Connection, p: InputButton) -> None:
        self._mouse.click(p.button)
        self._held.get(conn.conn_id, set()).discard(p.button)

    async def _down(self, conn: Connection, p: InputButton) -> None:
        self._mouse.down(p.button)
        self._held.setdefault(conn.conn_id, set()).add(p.button)

    async def _up(self, conn: Connection, p: InputButton) -> None:
        self._mouse.up(p.button)
        self._held.get(conn.conn_id, set()).discard(p.button)

    async def _scroll(self, _conn: Connection, p: InputScroll) -> None:
        self._mouse.scroll(p.dx, p.dy)

    async def _zoom(self, _conn: Connection, p: InputZoom) -> None:
        self._keyboard.zoom(p.dir)

    async def _key_press(self, _conn: Connection, p: KeyPress) -> None:
        try:
            self._keyboard.press(p.key, p.modifiers)
        except UnsupportedKeyError as exc:
            raise ActionError(f"The {p.key} key isn't available on this laptop.") from exc

    async def _key_text(self, _conn: Connection, p: KeyText) -> None:
        # Typing up to 2000 characters takes a moment, so keep the event loop free.
        await asyncio.to_thread(self._keyboard.type_text, p.text)

    async def _release_for(self, conn: Connection) -> None:
        held = self._held.pop(conn.conn_id, set())
        if not held or self._devices.mouse is None:
            return
        for button in held:
            self._devices.mouse.up(button)
        log_event(log, "released_buttons", conn=conn.conn_id, buttons=sorted(held))


def register_input(agent: Agent, devices: InputDevices) -> InputService:
    service = InputService(agent, devices)
    service.register()
    return service
