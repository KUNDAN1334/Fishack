"""Conversational intents that must never reach retrieval.

Why this exists
---------------
The confidence gate sits BEFORE generation, which is the right design for
questions and the wrong one for "hi". A greeting retrieves nothing, scores
below threshold, and abstains — technically correct, and it reads as broken.
Worse, it opens an escalation, so a user saying hello lands a ticket in a human
agent's queue.

Why it is a matcher and not a prompt
------------------------------------
The obvious fix is to let the model handle greetings. That fails on the thing
this system exists to protect: once the model is allowed to answer without
retrieved context, it is allowed to answer ANY question without retrieved
context, and the closed-book guarantee is gone. A greeting is not a retrieval
problem, so it should not enter the retrieval pipeline at all.

So: a pure function, no LLM call, no database read, deterministic, and testable
without any infrastructure. Zero tokens, roughly zero milliseconds.

The safety property, and how it is enforced
-------------------------------------------
This must NEVER swallow a real question. The golden set contains 16
`out_of_scope` cases that MUST abstain, and an over-eager matcher here would
turn a must-abstain assertion into a cheerful non-answer — the exact failure
mode the whole system is built against.

Two rules keep it narrow:

  1. Every pattern is ANCHORED to the whole message. "hi" matches; "hi, what is
     the webhook retry limit?" does not, and falls through to the pipeline.
  2. The pattern list is a closed set of literal phrasings. There is no fuzzy
     matching, no embedding similarity, no "starts with a greeting" heuristic —
     each of those would put a real question at risk to save a rare keystroke.

`tests/test_smalltalk.py` asserts both directions: that greetings match, and
that every out-of-scope query from the golden set does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# What Fishack says about itself. Deliberately short — someone asking "what are
# you" wants one sentence and a suggestion of what to type next, not a tour.
# The three clauses map to the three promises the UI makes observable, so the
# self-description and the product cannot drift apart.
ABOUT: Final[str] = (
    "I'm Fishack — a support assistant for Flowlytics. I answer only from your "
    "own documentation: every claim I make carries a citation you can open, and "
    "when the docs can't support an answer I say so and escalate to a human "
    "instead of guessing. Ask me about webhooks, rate limits, billing, or an "
    "error code like ERR_TIMEOUT_502."
)

GREETING: Final[str] = (
    "Hello. I answer Flowlytics support questions from your documentation — try "
    "asking about webhooks, rate limits, billing, or an error code like "
    "ERR_TIMEOUT_502."
)

THANKS: Final[str] = "You're welcome. Ask me anything else about your Flowlytics documentation."

GOODBYE: Final[str] = "Goodbye."


@dataclass(frozen=True)
class Smalltalk:
    """A matched conversational intent and the fixed reply for it."""

    kind: str  # 'greeting' | 'about' | 'thanks' | 'goodbye'
    reply: str


# Each entry is (compiled pattern, kind, reply). Patterns are matched against a
# NORMALISED message (see `_normalise`) and are fully anchored by `fullmatch`.
#
# On the phrasings included: these are what people actually type into a chat box
# as a whole message. Anything longer is a question, and a question belongs in
# the pipeline even when it happens to be about Fishack itself — "how does your
# retrieval work" should retrieve, not recite a canned line.
_RULES: Final[tuple[tuple[re.Pattern[str], str, str], ...]] = (
    (
        re.compile(
            r"(hi|hii+|hey+|heyy+|hello+|helo|yo|sup|hiya|heya|howdy|namaste|greetings)"
            r"( there| fishack| bot)?"
        ),
        "greeting",
        GREETING,
    ),
    (
        re.compile(r"good (morning|afternoon|evening|day)"),
        "greeting",
        GREETING,
    ),
    (
        re.compile(
            r"(who|what) (are|r) (you|u)"
            r"|tell me about (you|yourself|fishack)"
            r"|what (is|are) (you|fishack)"
            r"|what (can|do) (you|u) do"
            r"|what can (i|you) (ask|help)( with| me with)?"
            r"|how (do|does) (you|this|fishack) work"
            r"|introduce yourself"
            r"|about (you|yourself|fishack)"
            r"|help"
        ),
        "about",
        ABOUT,
    ),
    (
        re.compile(r"(thanks|thank you|thankyou|ty|thx|cheers|nice|great|perfect|awesome)( a lot| so much| you)?"),
        "thanks",
        THANKS,
    ),
    (
        re.compile(r"(bye+|goodbye|see (you|ya)|good ?night|later)"),
        "goodbye",
        GOODBYE,
    ),
)

# Trailing decoration people add to a greeting. Stripped before matching so
# "hi!!" and "hello :)" behave like "hi" — without loosening the anchoring,
# which is what actually keeps real questions out.
_TRAILING = re.compile(r"[\s!.?,~:;()\[\]<>\-—*'\"]+$")
_LEADING = re.compile(r"^[\s!.?,~:;()\[\]<>\-—*'\"]+")
# Emoji and other symbol/pictograph codepoints, removed the same way.
_PICTOGRAPHS = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\U00002190-\U000021FF]+"
)


def _normalise(query: str) -> str:
    """Lowercase, drop emoji and edge punctuation, collapse inner whitespace.

    Nothing here widens what matches — it only removes decoration that carries
    no meaning. The `fullmatch` in `classify` is what keeps the set narrow.
    """
    text = _PICTOGRAPHS.sub(" ", query.lower())
    text = " ".join(text.split())
    text = _LEADING.sub("", text)
    text = _TRAILING.sub("", text)
    return text


# A message longer than this is a question, whatever it starts with. Cheap
# guard so a long message never even reaches the patterns.
_MAX_LENGTH: Final[int] = 40


def classify(query: str) -> Smalltalk | None:
    """Return a fixed reply for a conversational message, or None.

    None means "this is a question" — the caller runs the normal pipeline. That
    is the default for anything not on the list, which is the safe direction to
    fail in: an unmatched greeting is a mildly awkward abstention, whereas a
    matched question is a confident non-answer to something the corpus could
    have answered.
    """
    text = _normalise(query)
    if not text or len(text) > _MAX_LENGTH:
        return None

    for pattern, kind, reply in _RULES:
        if pattern.fullmatch(text):
            return Smalltalk(kind=kind, reply=reply)
    return None
