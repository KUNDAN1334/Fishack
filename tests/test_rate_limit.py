"""Backoff math + retry loop behavior. compute_delay is a pure function so
the interesting properties are directly assertable."""

import asyncio

import pytest

from app.llm.base import AuthError, RateLimitError
from app.llm.rate_limit import (
    RetryPolicy,
    call_with_retries,
    compute_delay,
    is_quota_exhausted,
)
from tests.fakes import FakeProvider

NO_JITTER = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=20.0, jitter_fraction=0.0)
FAST = RetryPolicy(max_attempts=3, base_delay=0.001, max_delay=0.002)


def test_exponential_growth():
    assert compute_delay(1, NO_JITTER) == 1.0
    assert compute_delay(2, NO_JITTER) == 2.0
    assert compute_delay(3, NO_JITTER) == 4.0


def test_max_delay_caps_backoff():
    assert compute_delay(10, NO_JITTER) == 20.0  # 512s uncapped


def test_retry_after_wins_when_longer():
    # Server said "wait 5s", our backoff said 1s -> respect the server
    assert compute_delay(1, NO_JITTER, retry_after=5.0) == 5.0
    # Server said 0.5s but our backoff is already 2s -> keep the larger
    assert compute_delay(2, NO_JITTER, retry_after=0.5) == 2.0


def test_jitter_stays_in_bounds():
    policy = RetryPolicy(base_delay=1.0, jitter_fraction=0.25)
    for _ in range(50):
        delay = compute_delay(1, policy)
        assert 1.0 <= delay <= 1.25


async def test_retries_then_succeeds():
    provider = FakeProvider("p", ["rate_limit", "rate_limit", "ok"])
    result = await call_with_retries(
        lambda: provider.complete([], temperature=0.0, max_tokens=10), FAST
    )
    assert result.text == "fake answer"
    assert provider.calls == 3


async def test_exhausted_retries_raise_last_error():
    provider = FakeProvider("p", ["rate_limit"])
    with pytest.raises(RateLimitError):
        await call_with_retries(
            lambda: provider.complete([], temperature=0.0, max_tokens=10), FAST
        )
    assert provider.calls == FAST.max_attempts  # tried exactly max_attempts times


async def test_auth_error_not_retried():
    provider = FakeProvider("p", ["auth"])
    with pytest.raises(AuthError):
        await call_with_retries(
            lambda: provider.complete([], temperature=0.0, max_tokens=10), FAST
        )
    assert provider.calls == 1  # no retries on a bad key


# ------------------------------------------------- quota exhaustion (Phase 2) --
# A 429 with a huge Retry-After is a DIFFERENT situation from a burst limit:
# the provider is out for the day. Sleeping max_delay first only delays the
# failover that was always going to happen. (ADR-006 footnote.)


def test_is_quota_exhausted_boundary():
    policy = RetryPolicy(max_delay=20.0)
    assert is_quota_exhausted(None, policy) is False      # no header at all
    assert is_quota_exhausted(5.0, policy) is False       # ordinary burst limit
    assert is_quota_exhausted(20.0, policy) is False      # exactly at the cap: still waitable
    assert is_quota_exhausted(20.1, policy) is True       # just over -> un-waitable
    assert is_quota_exhausted(3600.0, policy) is True     # daily quota gone


async def test_quota_exhaustion_fails_over_without_sleeping(monkeypatch):
    """The behavior that motivated the change: zero sleeps, one attempt."""
    slept: list[float] = []

    async def spy_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", spy_sleep)

    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=20.0)
    provider = FakeProvider("p", ["rate_limit"], retry_after=3600.0)

    with pytest.raises(RateLimitError):
        await call_with_retries(
            lambda: provider.complete([], temperature=0.0, max_tokens=10), policy
        )

    assert provider.calls == 1, "must not retry a provider that is out of quota"
    assert slept == [], "must not sleep before failing over"


async def test_ordinary_rate_limit_still_sleeps_and_retries(monkeypatch):
    """Guard against over-correcting: a short Retry-After must still be waited
    out on the SAME provider — failing over on every burst limit would abandon
    our preferred provider constantly."""
    slept: list[float] = []

    async def spy_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", spy_sleep)

    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=20.0, jitter_fraction=0.0)
    provider = FakeProvider("p", ["rate_limit", "ok"], retry_after=2.0)

    result = await call_with_retries(
        lambda: provider.complete([], temperature=0.0, max_tokens=10), policy
    )

    assert result.text == "fake answer"
    assert provider.calls == 2
    assert slept == [2.0]  # server's Retry-After beat our 1s backoff
