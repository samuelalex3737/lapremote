"""OS media keys, used when no media session API is available (or nothing is listed)."""

from __future__ import annotations

from lapremote.input.keyboard import Keyboard, UnsupportedKeyError
from lapremote.media.base import MediaCommand

MEDIA_KEYS: dict[MediaCommand, str] = {
    # There are no separate play and pause keys, only play/pause.
    "toggle": "media_play_pause",
    "play": "media_play_pause",
    "pause": "media_play_pause",
    "next": "media_next",
    "prev": "media_prev",
}
VOLUME_KEYS = {"up": "volume_up", "down": "volume_down", "mute": "volume_mute"}

# One volume key press moves the system volume by about this many percent (Windows and macOS).
PERCENT_PER_VOLUME_KEY = 2


class MediaKeys:
    def __init__(self, keyboard: Keyboard | None) -> None:
        self._keyboard = keyboard

    @property
    def available(self) -> bool:
        return self._keyboard is not None

    def press(self, key: str, times: int = 1) -> bool:
        if self._keyboard is None:
            return False
        try:
            for _ in range(times):
                self._keyboard.press(key)
        except UnsupportedKeyError:
            return False
        return True

    def command(self, action: MediaCommand) -> bool:
        return self.press(MEDIA_KEYS[action])

    def volume_step(self, delta: int) -> bool:
        presses = max(1, round(abs(delta) / PERCENT_PER_VOLUME_KEY))
        return self.press(VOLUME_KEYS["up" if delta > 0 else "down"], presses)

    def toggle_mute(self) -> bool:
        return self.press(VOLUME_KEYS["mute"])
