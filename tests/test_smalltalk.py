"""Tests for the conversational-intent matcher.

Two directions, and the second one is the one that matters. Matching greetings
is a convenience; NOT matching a real question is a correctness property, and
the golden set is the strongest available statement of what a real question
looks like in this system.

Pure tests — no Postgres, no Redis, no model. They run in `make test-unit`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.generation.smalltalk import ABOUT, GREETING, classify

# --------------------------------------------------------------- matching --

GREETINGS = [
    "hi", "Hi", "HI", "hii", "hiii", "hey", "heyy", "hello", "Hello!", "helo",
    "yo", "sup", "hiya", "heya", "howdy", "namaste", "greetings",
    "hi there", "hello there", "hey fishack",
    "Good morning", "good afternoon", "good evening", "good day",
    "hi!!", "hello.", "hey...", "hi 👋", "hello :)", "  hi  ",
]

ABOUT_QUESTIONS = [
    "who are you", "Who are you?", "what are you", "what r u", "who r u",
    "tell me about you", "tell me about yourself", "tell me about fishack",
    "what is fishack", "what can you do", "what do you do",
    "what can i ask", "how do you work", "how does this work",
    "introduce yourself", "about you", "help",
]

COURTESIES = [
    "thanks", "Thank you", "thankyou", "ty", "thx", "cheers", "thanks a lot",
    "bye", "byee", "goodbye", "see you", "see ya", "good night", "later",
]


@pytest.mark.parametrize("query", GREETINGS)
def test_greetings_are_answered_without_touching_the_pipeline(query):
    result = classify(query)
    assert result is not None, f"{query!r} should be recognised as a greeting"
    assert result.kind == "greeting"
    assert result.reply == GREETING


@pytest.mark.parametrize("query", ABOUT_QUESTIONS)
def test_identity_questions_get_the_about_line(query):
    result = classify(query)
    assert result is not None, f"{query!r} should be recognised"
    assert result.kind == "about"
    assert result.reply == ABOUT


@pytest.mark.parametrize("query", COURTESIES)
def test_courtesies_are_acknowledged(query):
    assert classify(query) is not None


# ------------------------------------------------------------ NOT matching --
#
# Everything below must fall through to the real pipeline. A false positive
# here is a confident non-answer to a question the corpus could have answered,
# which is strictly worse than the awkward abstention this feature removes.

REAL_QUESTIONS = [
    # A greeting followed by a question is a question.
    "hi, what is the webhook retry limit?",
    "hello can you tell me about webhook retries",
    "hey what causes ERR_TIMEOUT_502",
    "thanks for that, what about the backoff?",
    # Phrasings that share words with the patterns but ask something real.
    "what are the rate limits",
    "what are you charging me for this month",
    "who are the admins on my account",
    "tell me about the billing plans",
    "what can you do with webhooks",
    "help me understand proration",
    "how does webhook retry work",
    "about your rate limits",
    "what do you do about failed webhooks",
    # The canonical out-of-scope case. MUST still abstain.
    "What is the capital of France?",
]


@pytest.mark.parametrize("query", REAL_QUESTIONS)
def test_real_questions_are_never_swallowed(query):
    assert classify(query) is None, f"{query!r} must reach the pipeline"


def test_empty_and_whitespace_fall_through():
    # The route rejects these with a 422 before the pipeline sees them; the
    # matcher must not claim them either.
    assert classify("") is None
    assert classify("   ") is None


def test_a_long_message_is_always_a_question():
    assert classify("hi " * 40) is None


# ---------------------------------------------------- the safety guarantee --


def _golden_cases():
    path = Path(__file__).resolve().parents[1] / "data" / "golden" / "golden_set.jsonl"
    if not path.exists():  # pragma: no cover — corpus is committed, but be kind
        pytest.skip("golden set not present")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_no_golden_case_is_intercepted():
    """The load-bearing test.

    If the matcher ever swallows a golden-set query, the eval harness silently
    starts scoring a canned string instead of the pipeline — and 16 must-abstain
    assertions would begin passing for entirely the wrong reason.
    """
    intercepted = []
    for case in _golden_cases():
        if classify(case["query"]) is not None:
            intercepted.append((case["case_id"], case["case_type"], case["query"]))
        for turn in case.get("history") or []:
            if turn.get("role") == "user" and classify(turn["content"]) is not None:
                intercepted.append((case["case_id"], "history", turn["content"]))

    assert not intercepted, f"matcher intercepted golden-set queries: {intercepted}"


def test_the_about_text_states_all_three_promises():
    """The self-description and the product must not drift apart.

    Someone asking "what are you" is told it cites, that it works only from
    their documentation, and that it escalates rather than guessing. Those are
    the three properties the UI exists to make observable; if one is removed
    here, the answer starts overselling or underselling what was built.
    """
    lowered = ABOUT.lower()
    assert "citation" in lowered
    assert "documentation" in lowered
    assert "escalate" in lowered
