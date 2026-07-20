"""Retry policy: exponential backoff with jitter for rate limits and
transient failures.

This is free-tier survival AND the exact pattern paid production systems use
— providers throttle everyone eventually. The fallback CHAIN (client.py)
decides which provider to call; this module decides how patiently to retry
ONE provider before giving up on it.
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

from pydantic import BaseModel

from app.llm.base import RateLimitError, TransientError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    base_delay: float = 1.0   # seconds; attempt n waits base * 2^(n-1)
    max_delay: float = 20.0   # cap so retry_after or deep backoff can't stall forever
    # Jitter prevents the "thundering herd": if many clients hit a 429 at the
    # same moment and all retry after exactly 2s, they collide again. Adding
    # 0-25% random extra spreads them out.
    jitter_fraction: float = 0.25


def compute_delay(attempt: int, policy: RetryPolicy, retry_after: float | None = None) -> float:
    """Delay before retry number `attempt` (1-based).

    Pure function — unit-tested directly. Honors the provider's Retry-After
    if it's LONGER than our backoff (the server knows its own limits better
    than we do), still capped at max_delay.
    """
    delay = policy.base_delay * (2 ** (attempt - 1))
    if retry_after is not None:
        delay = max(delay, retry_after)
    delay = min(delay, policy.max_delay)
    if policy.jitter_fraction > 0:
        delay += random.uniform(0, delay * policy.jitter_fraction)
    return delay


async def call_with_retries(
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
) -> T:
    """Run `fn`, retrying on RateLimitError/TransientError with backoff.

    Anything else (AuthError, parsing bugs) is NOT retried — it propagates
    immediately so the fallback chain can act. After max_attempts the last
    error propagates, which is the chain's signal to fail over.
    """
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except (RateLimitError, TransientError) as exc:
            last_error = exc
            if attempt == policy.max_attempts:
                break
            retry_after = getattr(exc, "retry_after", None)
            delay = compute_delay(attempt, policy, retry_after)
            logger.warning(
                "retryable error (attempt %d/%d), sleeping %.2fs: %s",
                attempt, policy.max_attempts, delay, exc,
            )
            await asyncio.sleep(delay)
    assert last_error is not None  # loop always sets it before breaking
    raise last_error
