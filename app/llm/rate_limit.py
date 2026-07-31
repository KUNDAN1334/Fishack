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


def is_quota_exhausted(retry_after: float | None, policy: RetryPolicy) -> bool:
    """Does this Retry-After mean "your daily quota is gone", not "slow down"?

    Free tiers signal two very different situations with the same HTTP 429:

      Retry-After: 2      -> a momentary burst limit. Sleeping 2s and retrying
                             the SAME provider is right; failing over would
                             waste the provider we prefer.
      Retry-After: 3600   -> the daily/hourly quota is spent. This provider is
                             dead for the rest of the window. Sleeping is
                             pointless, and sleeping `max_delay` first (which
                             is what we used to do) just adds 20s of latency
                             before the failover that was always going to
                             happen.

    The dividing line is `max_delay`: it is already defined as "the longest we
    are ever willing to wait on one provider". Any Retry-After above it is, by
    our own policy, un-waitable — so treat it as a signal to move on NOW.

    Pure function so the boundary is directly unit-testable.
    """
    if retry_after is None:
        return False
    return retry_after > policy.max_delay


def compute_delay(attempt: int, policy: RetryPolicy, retry_after: float | None = None) -> float:
    """Delay before retry number `attempt` (1-based).

    Pure function — unit-tested directly. Honors the provider's Retry-After
    if it's LONGER than our backoff (the server knows its own limits better
    than we do), still capped at max_delay.

    NOTE: the cap is why `is_quota_exhausted` exists. Capping a 3600s
    Retry-After down to 20s does not make the provider answer in 20s — it just
    makes us wait 20s and fail anyway. The cap is correct for *waiting*; the
    caller must decide separately whether waiting is worth it at all.
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

    One early exit: a 429 whose Retry-After exceeds `max_delay` means the
    provider's quota is exhausted, not busy (see `is_quota_exhausted`). We
    raise straight away so `LLMClient` fails over to the next provider without
    burning a `max_delay` sleep on a provider that is dead for the day.
    """
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except (RateLimitError, TransientError) as exc:
            last_error = exc
            retry_after = getattr(exc, "retry_after", None)

            # Quota exhausted -> do not sleep, do not retry, fail over now.
            if is_quota_exhausted(retry_after, policy):
                logger.warning(
                    "quota exhausted on attempt %d/%d (Retry-After %.0fs > max_delay %.0fs); "
                    "failing over immediately instead of sleeping: %s",
                    attempt, policy.max_attempts, retry_after, policy.max_delay, exc,
                )
                raise

            if attempt == policy.max_attempts:
                break
            delay = compute_delay(attempt, policy, retry_after)
            logger.warning(
                "retryable error (attempt %d/%d), sleeping %.2fs: %s",
                attempt, policy.max_attempts, delay, exc,
            )
            await asyncio.sleep(delay)
    assert last_error is not None  # loop always sets it before breaking
    raise last_error
