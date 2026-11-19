"""Decide how to seek: through the session API when it can, or with site keys in the browser.

Keys are only ever sent when the foreground window is a browser, so a seek never
types into some other app by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

from lapremote.media.base import SessionSnapshot
from lapremote.system.context import ForegroundInfo

# site -> ((back key, forward key), seconds per press)
SITE_KEYS: dict[str, tuple[tuple[str, str], float]] = {
    "youtube": (("j", "l"), 10.0),
    "netflix": (("left", "right"), 10.0),
    "prime": (("left", "right"), 10.0),
    "generic": (("left", "right"), 5.0),
    "spotify_web": (("left", "right"), 5.0),
}
MAX_PRESSES = 60

NOT_IN_FRONT = "Bring the browser with the video to the front, then try again."
NO_ABSOLUTE = "This player can only skip in steps. Use the back and forward buttons."
NOTHING_PLAYING = "Nothing is playing right now."


@dataclass(frozen=True)
class ApiSeek:
    seconds: float


@dataclass(frozen=True)
class KeySeek:
    key: str
    presses: int
    seconds_per_press: float


@dataclass(frozen=True)
class SeekRefused:
    reason: str


SeekPlan = ApiSeek | KeySeek | SeekRefused


def plan_seek(
    session: SessionSnapshot | None,
    *,
    to: float | None,
    by: float | None,
    foreground: ForegroundInfo | None,
    now_ms: float | None = None,
) -> SeekPlan:
    if session is not None and session.can_seek:
        if to is not None:
            target = to
        else:
            current = session.position_now(now_ms)
            if current is None:
                return SeekRefused(NOTHING_PLAYING)
            target = current + (by or 0.0)
        target = max(0.0, target)
        if session.duration is not None:
            target = min(target, max(0.0, session.duration - 0.5))
        return ApiSeek(target)

    if foreground is None or foreground.category != "browser":
        return SeekRefused(NOT_IN_FRONT)
    if by is None:
        return SeekRefused(NO_ABSOLUTE)
    (back, forward), step = SITE_KEYS[foreground.site or "generic"]
    presses = min(MAX_PRESSES, max(1, round(abs(by) / step)))
    return KeySeek(key=forward if by > 0 else back, presses=presses, seconds_per_press=step)
