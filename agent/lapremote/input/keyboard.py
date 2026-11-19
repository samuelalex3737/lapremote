"""Key presses, combos and text from the allowlisted key names in protocol.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from lapremote.protocol import KEY_NAMES, Modifier, OsName

if TYPE_CHECKING:
    from pynput.keyboard import Key, KeyCode

# Allowlisted key name -> pynput ``Key`` attribute for non-character keys.
SPECIAL_KEYS: dict[str, str] = {
    "enter": "enter",
    "esc": "esc",
    "tab": "tab",
    "backspace": "backspace",
    "delete": "delete",
    "insert": "insert",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "pagedown": "page_down",
    "capslock": "caps_lock",
    "printscreen": "print_screen",
    "menu": "menu",
    "media_play_pause": "media_play_pause",
    "media_next": "media_next",
    "media_prev": "media_previous",
    "volume_up": "media_volume_up",
    "volume_down": "media_volume_down",
    "volume_mute": "media_volume_mute",
    **{f"f{n}": f"f{n}" for n in range(1, 25)},
}
MODIFIER_KEYS: dict[Modifier, str] = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "meta": "cmd"}
CHAR_KEYS = frozenset(k for k in KEY_NAMES if len(k) == 1)

ZOOM_MODIFIER: dict[OsName, Modifier] = {"windows": "ctrl", "linux": "ctrl", "macos": "meta"}


class UnsupportedKeyError(ValueError):
    """The key exists in the protocol but not on this OS (for example Insert on a Mac)."""


class KeyboardBackend(Protocol):
    def resolve(self, name: str) -> object:
        """Map an allowlisted key name or modifier attribute to an opaque backend key."""
        ...

    def press(self, key: object) -> None: ...
    def release(self, key: object) -> None: ...
    def type(self, text: str) -> None: ...


class Keyboard:
    def __init__(self, backend: KeyboardBackend, os_name: OsName) -> None:
        self._backend = backend
        self._os = os_name

    def press(self, key: str, modifiers: Sequence[Modifier] = ()) -> None:
        if key not in CHAR_KEYS and key not in SPECIAL_KEYS:
            msg = f"key {key!r} is not allowlisted"
            raise UnsupportedKeyError(msg)
        main = self._backend.resolve(key)
        mods = [self._backend.resolve(MODIFIER_KEYS[m]) for m in modifiers]
        pressed: list[object] = []
        try:
            for mod in mods:
                self._backend.press(mod)
                pressed.append(mod)
            self._backend.press(main)
            self._backend.release(main)
        finally:
            for mod in reversed(pressed):
                self._backend.release(mod)

    def zoom(self, direction: str) -> None:
        self.press("=" if direction == "in" else "-", [ZOOM_MODIFIER[self._os]])

    def type_text(self, text: str) -> None:
        self._backend.type(text)


class PynputKeyboard:
    """KeyboardBackend on top of pynput."""

    def __init__(self) -> None:
        from pynput import keyboard  # noqa: PLC0415 - imported lazily: fails without a display

        self._keyboard = keyboard
        self._controller = keyboard.Controller()

    def resolve(self, name: str) -> object:
        if len(name) == 1:
            return self._keyboard.KeyCode.from_char(name)
        attr = SPECIAL_KEYS.get(name, name)
        key: object = getattr(self._keyboard.Key, attr, None)
        if key is None:
            msg = f"{name} isn't available on this laptop"
            raise UnsupportedKeyError(msg)
        return key

    def _checked(self, key: object) -> Key | KeyCode:
        if isinstance(key, (self._keyboard.Key, self._keyboard.KeyCode)):
            return key
        msg = f"not a pynput key: {key!r}"
        raise TypeError(msg)

    def press(self, key: object) -> None:
        self._controller.press(self._checked(key))

    def release(self, key: object) -> None:
        self._controller.release(self._checked(key))

    def type(self, text: str) -> None:
        self._controller.type(text)
