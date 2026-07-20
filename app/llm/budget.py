"""Per-provider usage counters + virtual-cost accounting (Redis).

Two jobs (Design.md §12 "cost per query" + free-tier requirement #2):
  1. Quota visibility — how much of each provider's free daily allowance
     have we burned? (requests + tokens, per provider, per UTC day)
  2. Virtual cost — what WOULD this usage cost at paid-API prices, so the
     README/stats can report cost-per-query with real methodology.

Why Redis and not Postgres: these are high-frequency increments of ephemeral
daily counters — Redis INCR is atomic and O(1). The durable per-request
record lives in the traces table; if Redis restarts we lose only the current
day's aggregate view, not observability.
"""

import datetime as dt

import redis.asyncio as aioredis

from app.config import DEFAULT_VIRTUAL_PRICE, VIRTUAL_PRICES, ModelPrice
from app.llm.base import TokenUsage

# Counters auto-expire after 3 days: yesterday stays visible for comparison,
# but keys can never accumulate forever.
COUNTER_TTL_SECONDS = 3 * 24 * 3600


def virtual_cost_usd(model: str, usage: TokenUsage) -> float:
    """Cost this call WOULD incur at paid prices (see VIRTUAL_PRICES for the
    methodology)."""
    price: ModelPrice = VIRTUAL_PRICES.get(model, DEFAULT_VIRTUAL_PRICE)
    return (
        usage.input_tokens * price.input_per_million
        + usage.output_tokens * price.output_per_million
    ) / 1_000_000


class BudgetTracker:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    @staticmethod
    def _key(provider: str, field: str, day: dt.date | None = None) -> str:
        # UTC so the "day" boundary matches most providers' quota resets
        day = day or dt.datetime.now(dt.timezone.utc).date()
        return f"budget:{day.isoformat()}:{provider}:{field}"

    async def record(self, provider: str, model: str, usage: TokenUsage) -> float:
        """Record one completed call; returns its virtual cost in USD.

        Pipelined: 4 increments in one round trip. Never raises on Redis
        failure at call sites — callers treat budget tracking as best-effort
        (an LLM answer must not fail because a counter did).
        """
        cost = virtual_cost_usd(model, usage)
        pipe = self.redis.pipeline()
        for field, amount in (
            ("requests", 1),
            ("tokens_in", usage.input_tokens),
            ("tokens_out", usage.output_tokens),
        ):
            key = self._key(provider, field)
            pipe.incrby(key, amount)
            pipe.expire(key, COUNTER_TTL_SECONDS)
        cost_key = self._key(provider, "virtual_cost_usd")
        pipe.incrbyfloat(cost_key, cost)
        pipe.expire(cost_key, COUNTER_TTL_SECONDS)
        await pipe.execute()
        return cost

    async def snapshot(self, day: dt.date | None = None) -> dict[str, dict[str, float]]:
        """Today's usage per provider — feeds /stats (Phase 5) and smoke_test.

        SCAN (not KEYS) to avoid blocking Redis; fine at this key count
        either way, but the habit matters.
        """
        day = day or dt.datetime.now(dt.timezone.utc).date()
        pattern = f"budget:{day.isoformat()}:*"
        result: dict[str, dict[str, float]] = {}
        async for key in self.redis.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            _, _, provider, field = key_str.split(":", 3)
            raw = await self.redis.get(key_str)
            value = float(raw) if raw is not None else 0.0
            result.setdefault(provider, {})[field] = (
                value if field == "virtual_cost_usd" else int(value)
            )
        return result
