"""Query rewriting (Design.md §2 step 2).

The rewriter's failure modes are all silent: a bad rewrite does not raise, it
retrieves the wrong thing, and you spend a day debugging the retriever. So the
output validation gets more test coverage than the happy path.
"""

import pytest

from app.generation.models import Turn
from app.generation.rewriter import (
    QueryRewriter,
    clean_rewrite,
    looks_like_a_rewrite,
)
from app.llm.base import LLMResponse, TokenUsage


class StubLLM:
    """Returns a scripted rewrite, or raises."""

    def __init__(self, text: str = "", error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls = 0
        self.last_messages = None
        self.last_temperature = None

    async def complete(self, messages, *, temperature=None, max_tokens=None):
        self.calls += 1
        self.last_messages = messages
        self.last_temperature = temperature
        if self.error:
            raise self.error
        return LLMResponse(
            text=self.text, provider="stub", model="stub-1", usage=TokenUsage()
        )


HISTORY = [
    Turn(role="user", content="Why is my webhook failing after the v2.3 update?"),
    Turn(role="assistant", content="Webhook deliveries retry up to 3 times [1]."),
]


# ------------------------------------------------------------- skip paths --


async def test_first_turn_is_never_rewritten():
    """The common case, and it must cost nothing. A question with no
    conversation behind it is standalone by definition — rewriting can only
    paraphrase it, at the price of a round trip and a chance to mangle an
    error code."""
    llm = StubLLM("should not be called")
    result = await QueryRewriter(llm).rewrite("How do I rotate my API key?", [])

    assert llm.calls == 0
    assert result.skipped_reason == "first_turn"
    assert result.effective_query == "How do I rotate my API key?"
    assert result.changed is False


async def test_disabled_rewriter_skips_without_calling():
    llm = StubLLM("x")
    result = await QueryRewriter(llm, enabled=False).rewrite("what about retries?", HISTORY)
    assert llm.calls == 0
    assert result.skipped_reason == "disabled"


# ----------------------------------------------------------- happy path --


async def test_follow_up_is_resolved_into_a_standalone_query():
    llm = StubLLM("What is the retry logic for webhook failures after the v2.3 update?")
    result = await QueryRewriter(llm).rewrite("what about the retry logic?", HISTORY)

    assert llm.calls == 1
    assert result.changed is True
    assert "webhook" in result.effective_query
    assert result.elapsed_ms >= 0


async def test_rewriting_runs_at_temperature_zero():
    """A mechanical transformation, not writing. Sampling here is pure
    downside — it can only introduce variation into a search key."""
    llm = StubLLM("What is the webhook retry logic?")
    await QueryRewriter(llm).rewrite("what about it?", HISTORY)
    assert llm.last_temperature == 0.0


async def test_history_is_truncated_to_the_configured_window():
    """Older turns are usually a different problem, and including them makes
    the rewriter drag stale entities into the query — subtler than truncating
    too hard."""
    long_history = [
        Turn(role="user" if i % 2 == 0 else "assistant", content=f"turn {i}")
        for i in range(20)
    ]
    llm = StubLLM("standalone question about turn 19")
    await QueryRewriter(llm, history_turns=4).rewrite("and that?", long_history)

    transcript = llm.last_messages[-1].content
    assert "turn 19" in transcript
    assert "turn 5" not in transcript


async def test_unchanged_rewrite_is_not_marked_as_changed():
    """`changed` drives traces.rewritten_query, which is NULL when nothing
    happened — so "how many turns actually needed rewriting?" is a NOT NULL
    count rather than a string comparison."""
    llm = StubLLM("How do I rotate my API key?")
    result = await QueryRewriter(llm).rewrite("How do I rotate my API key?", HISTORY)
    assert result.changed is False


# ------------------------------------------------------- failure is safe --


async def test_llm_failure_falls_back_to_the_original_query():
    """A degraded rewrite gives worse retrieval; a raised exception gives no
    answer at all. Never fail the request over an optimization."""
    llm = StubLLM(error=RuntimeError("all providers failed"))
    result = await QueryRewriter(llm).rewrite("what about retries?", HISTORY)

    assert result.effective_query == "what about retries?"
    assert result.skipped_reason == "failed"


# ------------------------------------------------- output validation --


@pytest.mark.parametrize(
    "candidate,reason",
    [
        ("", "empty"),
        ("x" * 500, "too_long"),
        ("I don't have enough information to answer this confidently.", "looks_like_an_answer"),
        ("Sure, here is the rewritten question you asked for", "looks_like_an_answer"),
        ("First paragraph of an answer.\n\nSecond paragraph.", "multi_paragraph"),
    ],
)
def test_bad_rewrites_are_rejected(candidate, reason):
    """The dominant failure of a rewriting prompt is that the model ANSWERS
    instead of rewriting. An answer silently substituted for a query means
    searching the corpus for the text of a hallucinated response."""
    acceptable, why = looks_like_a_rewrite("what about retries?", candidate)
    assert acceptable is False
    assert why == reason


def test_a_reasonable_rewrite_is_accepted():
    acceptable, why = looks_like_a_rewrite(
        "what about it?", "What is the retry logic for webhook failures after v2.3?"
    )
    assert acceptable is True and why == "ok"


def test_growth_check_does_not_punish_legitimate_expansion():
    """Resolving a three-word follow-up SHOULD produce a much longer query.
    The growth rule only fires when the result is also long in absolute terms,
    or short queries could never be expanded at all."""
    acceptable, _ = looks_like_a_rewrite(
        "and that?", "What is the webhook retry limit after the v2.4 release?"
    )
    assert acceptable is True


async def test_a_rejected_rewrite_falls_back_and_records_why():
    llm = StubLLM("Sure, here is your answer: webhooks retry three times because...")
    result = await QueryRewriter(llm).rewrite("what about retries?", HISTORY)

    assert result.effective_query == "what about retries?"
    assert result.skipped_reason.startswith("rejected:")


# -------------------------------------------------------------- cleaning --


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"What is the retry limit?"', "What is the retry limit?"),
        ("STANDALONE QUESTION: What is the retry limit?", "What is the retry limit?"),
        ("  What is the retry limit?  ", "What is the retry limit?"),
        ("'What is the retry limit?'", "What is the retry limit?"),
    ],
)
def test_clean_rewrite_strips_model_decoration(raw, expected):
    assert clean_rewrite(raw) == expected


def test_clean_rewrite_keeps_an_unbalanced_quote():
    """An unbalanced quote is part of the user's actual text and must survive
    — stripping it would corrupt a query about, say, a quoting bug."""
    assert clean_rewrite("What does 'unclosed do?") == "What does 'unclosed do?"
