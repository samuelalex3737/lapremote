"""Relative mouse control with sub-pixel carry and per-OS scroll units.

Scroll values on the wire are in wheel notches (1.0 = one notch of a normal
mouse wheel; fractions allowed). ``dy > 0`` moves the view down the page and
``dx > 0`` moves it right.
"""

from __future__ import annotations

import math
from typing import Protocol

from lapremote.protocol import Button, OsName

# Smallest scroll step each OS backend can express, in notches.
#   windows: SendInput wheel data is in 1/120 notch (WHEEL_DELTA)
#   macos:   pynput sends pixel scroll events, 10 px per unit; 4 units per notch
#   linux:   X11 scroll is whole button-4/5 clicks
SCROLL_STEP: dict[OsName, float] = {"windows": 1 / 120, "macos": 0.25, "linux": 1.0}
# How pynput's ``scroll`` unit relates to one step above.
SCROLL_UNIT_PER_STEP: dict[OsName, float] = {"windows": 1 / 120, "macos": 1.0, "linux": 1.0}


class MouseBackend(Protocol):
    def move(self, dx: int, dy: int) -> None: ...
    def move_to(self, x: int, y: int) -> None:
        """Absolute position in physical screen pixels (virtual desktop coordinates)."""
        ...
    def press(self, button: Button) -> None: ...
    def release(self, button: Button) -> None: ...
    def scroll(self, dx: float, dy: float) -> None:
        """pynput semantics: positive dy scrolls the view up."""
        ...


class _Carry:
    """Accumulates fractional values and hands out whole steps."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0

    def take(self, dx: float, dy: float, step: float = 1.0) -> tuple[int, int]:
        self.x += dx / step
        self.y += dy / step
        ix = math.trunc(self.x)
        iy = math.trunc(self.y)
        self.x -= ix
        self.y -= iy
        return ix, iy


class Mouse:
    def __init__(self, backend: MouseBackend, os_name: OsName) -> None:
        self._backend = backend
        self._os = os_name
        self._move = _Carry()
        self._scroll = _Carry()
        self._held: set[Button] = set()

    @property
    def held(self) -> frozenset[Button]:
        return frozenset(self._held)

    def move(self, dx: float, dy: float) -> None:
        ix, iy = self._move.take(dx, dy)
        if ix or iy:
            self._backend.move(ix, iy)

    def click_at(self, x: int, y: int, button: Button) -> None:
        self._move = _Carry()
        self._backend.move_to(x, y)
        self.click(button)

    def click(self, button: Button) -> None:
        if button in self._held:
            # A click while the button is held (for example in drag lock) ends the drag.
            self.up(button)
            return
        self._backend.press(button)
        self._backend.release(button)

    def down(self, button: Button) -> None:
        if button in self._held:
            return
        self._backend.press(button)
        self._held.add(button)

    def up(self, button: Button) -> None:
        if button not in self._held:
            return
        self._backend.release(button)
        self._held.discard(button)

    def release_all(self) -> None:
        for button in list(self._held):
            self.up(button)

    def scroll(self, dx: float, dy: float) -> None:
        step = SCROLL_STEP[self._os]
        sx, sy = self._scroll.take(dx, dy, step)
        if sx or sy:
            unit = SCROLL_UNIT_PER_STEP[self._os]
            # Wire: dy > 0 means "view down"; pynput: dy > 0 means "scroll up".
            self._backend.scroll(sx * unit, -sy * unit)


class PynputMouse:
    """MouseBackend on top of pynput (SendInput / Quartz / XTest)."""

    def __init__(self) -> None:
        from pynput import mouse  # noqa: PLC0415 - imported lazily: fails without a display

        self._buttons = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }
        self._controller = mouse.Controller()

    def move(self, dx: int, dy: int) -> None:
        self._controller.move(dx, dy)

    def move_to(self, x: int, y: int) -> None:
        self._controller.position = (x, y)

    def press(self, button: Button) -> None:
        self._controller.press(self._buttons[button])

    def release(self, button: Button) -> None:
        self._controller.release(self._buttons[button])

    def scroll(self, dx: float, dy: float) -> None:
        # The stubs say int, but the Windows backend sends int(value * 120) wheel units,
        # so fractions give high-resolution scrolling. macOS and X11 get whole values.
        self._controller.scroll(dx, dy)  # type: ignore[arg-type]
