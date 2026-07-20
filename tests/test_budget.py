"""Budget tracker: counter math + virtual-cost calculation against
fakeredis (no docker required)."""

import fakeredis.aioredis
import pytest

from app.config import VIRTUAL_PRICES
from app.llm.base import TokenUsage
from app.llm.budget import BudgetTracker, virtual_cost_usd


@pytest.fixture
async def tracker():
    return BudgetTracker(fakeredis.aioredis.FakeRedis())


def test_virtual_cost_known_model():
    price = VIRTUAL_PRICES["llama-3.1-8b-instant"]
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    expected = price.input_per_million + price.output_per_million
    assert virtual_cost_usd("llama-3.1-8b-instant", usage) == pytest.approx(expected)


def test_virtual_cost_unknown_model_uses_default():
    # Unknown models must NOT be silently free — that would corrupt the
    # cost-per-query numbers
    cost = virtual_cost_usd("mystery-model-9000", TokenUsage(input_tokens=1000, output_tokens=1000))
    assert cost > 0


async def test_record_accumulates(tracker):
    await tracker.record("groq", "llama-3.1-8b-instant", TokenUsage(input_tokens=100, output_tokens=50))
    await tracker.record("groq", "llama-3.1-8b-instant", TokenUsage(input_tokens=200, output_tokens=25))
    snap = await tracker.snapshot()
    assert snap["groq"]["requests"] == 2
    assert snap["groq"]["tokens_in"] == 300
    assert snap["groq"]["tokens_out"] == 75
    assert snap["groq"]["virtual_cost_usd"] > 0


async def test_providers_tracked_separately(tracker):
    await tracker.record("groq", "llama-3.1-8b-instant", TokenUsage(input_tokens=10, output_tokens=10))
    await tracker.record("gemini", "gemini-2.5-flash", TokenUsage(input_tokens=20, output_tokens=20))
    snap = await tracker.snapshot()
    assert snap["groq"]["requests"] == 1
    assert snap["gemini"]["requests"] == 1
    assert snap["gemini"]["tokens_in"] == 20
