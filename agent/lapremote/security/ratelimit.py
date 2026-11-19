"""Rate limiters: a token bucket per connection and a sliding window per key."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

Clock = Callable[[], float]


@dataclass(frozen=True)
class Limits:
    """Defaults from the build spec."""

    messages_per_second: float = 300.0
    key_text_per_second: float = 10.0
    pair_attempts: int = 5
    pair_window_seconds: float = 60.0


class TokenBucket:
    """Allows bursts up to ``capacity`` and refills at ``rate`` tokens per second."""

    def __init__(
        self, rate: float, capacity: float | None = None, clock: Clock = time.monotonic
    ) -> None:
        if rate <= 0:
            msg = "rate must be positive"
            raise ValueError(msg)
        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._tokens = self._capacity
        self._clock = clock
        self._last = clock()

    def allow(self, cost: float = 1.0) -> bool:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False


class SlidingWindowLimiter:
    """At most ``limit`` events per ``window`` seconds for each key (for example an IP)."""

    def __init__(
        self, limit: int, window: float, clock: Clock = time.monotonic, max_keys: int = 4096
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        events = self._events.get(key)
        if events is None:
            if len(self._events) >= self._max_keys:
                self._prune(now)
            events = deque()
            self._events[key] = events
        while events and now - events[0] >= self._window:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True

    def _prune(self, now: float) -> None:
        stale = [k for k, ev in self._events.items() if not ev or now - ev[-1] >= self._window]
        for key in stale:
            del self._events[key]
        if len(self._events) >= self._max_keys:
            # Still full of active keys: drop the oldest to bound memory.
            oldest = min(self._events, key=lambda k: self._events[k][-1])
            del self._events[oldest]
