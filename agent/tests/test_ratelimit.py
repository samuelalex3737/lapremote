from __future__ import annotations

import pytest

from lapremote.security.ratelimit import Limits, SlidingWindowLimiter, TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_defaults_match_spec() -> None:
    limits = Limits()
    assert limits.messages_per_second == 300
    assert limits.key_text_per_second == 10
    assert limits.pair_attempts == 5
    assert limits.pair_window_seconds == 60


def test_bucket_allows_burst_then_refills() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=300, clock=clock)
    assert all(bucket.allow() for _ in range(300))
    assert not bucket.allow()
    clock.now += 0.1  # refills 30
    assert sum(bucket.allow() for _ in range(40)) == 30


def test_bucket_never_exceeds_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=10, clock=clock)
    clock.now += 100
    assert sum(bucket.allow() for _ in range(50)) == 10


def test_bucket_rejects_bad_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        TokenBucket(rate=0)


def test_sliding_window_per_key() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=5, window=60, clock=clock)
    assert all(limiter.allow("1.2.3.4") for _ in range(5))
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")
    clock.now += 59.9
    assert not limiter.allow("1.2.3.4")
    clock.now += 0.2
    assert limiter.allow("1.2.3.4")


def test_sliding_window_bounds_memory() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window=60, clock=clock, max_keys=3)
    for n in range(10):
        assert limiter.allow(f"ip{n}")
    assert len(limiter._events) <= 3
