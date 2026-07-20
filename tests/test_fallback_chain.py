"""The fallback chain — the riskiest logic in Phase 0.

Covers: failover order, failover event recording, auth short-circuit,
all-fail error, unconfigured-provider skipping, and the streaming
before/after-first-token failover rule.
"""

import pytest

from app.llm.base import ChatMessage, TransientError
from app.llm.client import AllProvidersFailedError, LLMClient
from app.llm.rate_limit import RetryPolicy
from tests.fakes import FakeProvider, MidStreamFailProvider

FAST = RetryPolicy(max_attempts=2, base_delay=0.001, max_delay=0.002)
MSG = [ChatMessage(role="user", content="hi")]


def make_client(*providers) -> LLMClient:
    return LLMClient(list(providers), retry_policy=FAST)


async def test_primary_success_no_failover():
    primary = FakeProvider("groq", ["ok"])
    backup = FakeProvider("gemini", ["ok"])
    response = await make_client(primary, backup).complete(MSG)
    assert response.provider == "groq"
    assert response.failover_events == []
    assert backup.calls == 0  # backup never touched


async def test_failover_to_second_provider():
    primary = FakeProvider("groq", ["rate_limit"])  # always 429
    backup = FakeProvider("gemini", ["ok"])
    response = await make_client(primary, backup).complete(MSG)
    assert response.provider == "gemini"
    # Primary was retried max_attempts times BEFORE failing over
    assert primary.calls == FAST.max_attempts
    assert len(response.failover_events) == 1
    assert response.failover_events[0]["provider"] == "groq"
    assert response.failover_events[0]["error_type"] == "RateLimitError"


async def test_auth_error_fails_over_without_retries():
    primary = FakeProvider("groq", ["auth"])
    backup = FakeProvider("gemini", ["ok"])
    response = await make_client(primary, backup).complete(MSG)
    assert response.provider == "gemini"
    assert primary.calls == 1  # bad key: no point retrying


async def test_all_providers_failed():
    with pytest.raises(AllProvidersFailedError) as excinfo:
        await make_client(
            FakeProvider("groq", ["rate_limit"]), FakeProvider("gemini", ["transient"])
        ).complete(MSG)
    tried = [e["provider"] for e in excinfo.value.failover_events]
    assert tried == ["groq", "gemini"]  # chain order preserved in the record


async def test_unconfigured_providers_skipped():
    client = make_client(
        FakeProvider("groq", ["ok"], configured=False), FakeProvider("gemini", ["ok"])
    )
    assert [p.name for p in client.providers] == ["gemini"]


async def test_empty_chain_is_loud_config_error():
    with pytest.raises(ValueError, match="No LLM providers configured"):
        make_client(FakeProvider("groq", ["ok"], configured=False))


async def test_stream_failover_before_first_token():
    primary = FakeProvider("groq", ["rate_limit"])
    backup = FakeProvider("gemini", ["ok"], text="hello world")
    events = [e async for e in make_client(primary, backup).stream(MSG)]
    deltas = [e.text for e in events if e.type == "delta"]
    done = events[-1]
    assert "".join(deltas).strip() == "hello world"
    assert done.response.provider == "gemini"
    assert len(done.response.failover_events) == 1


async def test_stream_no_failover_after_first_token():
    """Once the user has seen partial text, we must NOT silently restart the
    answer on another provider."""
    primary = MidStreamFailProvider("groq", ["ok"])
    backup = FakeProvider("gemini", ["ok"])
    stream = make_client(primary, backup).stream(MSG)
    received = []
    with pytest.raises(TransientError):
        async for event in stream:
            received.append(event)
    assert len(received) == 1  # the one delta that got out
    assert backup.calls == 0  # and no sneaky failover afterwards
