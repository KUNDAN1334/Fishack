"""Backoff math + retry loop behavior. compute_delay is a pure function so
the interesting properties are directly assertable."""

import pytest

from app.llm.base import AuthError, RateLimitError
from app.llm.rate_limit import RetryPolicy, call_with_retries, compute_delay
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
