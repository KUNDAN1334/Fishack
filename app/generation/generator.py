"""Grounded generation (Design.md §7).

Thin by design. Everything that makes the answer trustworthy lives elsewhere —
the gate decided we should generate, prompts.py shaped what the model sees,
citations.py checks what came back. This module's only jobs are to run the
call, stream it, and recognize an abstention.

The one non-obvious piece is abstention detection. The prompt tells the model
to emit a specific sentence verbatim, and three separate things must agree on
that string: the prompt, this detector, and Phase 4's hard assertions. It
lives in config as `abstention_message` for exactly that reason. But models do
not obey "verbatim" perfectly — they add a leading "Unfortunately," or swap a
contraction — so matching is normalized and prefix-based rather than exact.
Being strict here would mean a real abstention gets recorded as an answer,
which corrupts the escalation rate, the trace's `action` column, and the eval
harness's must-abstain checks all at once.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from app.generation.models import Citation, Turn
from app.generation.prompts import build_messages
from app.llm.base import LLMResponse, StreamEvent
from app.llm.client import LLMClient
from app.retrieval.models import ScoredChunk

logger = logging.getLogger(__name__)

# How much of the abstention sentence must match. The first clause ("I don't
# have enough information to answer this confidently") is distinctive enough
# that a false positive is implausible, while allowing the model to vary the
# second sentence.
_ABSTENTION_PREFIX_CHARS = 45


def _normalize(text: str) -> str:
    """Fold the variations models introduce: smart quotes, casing, whitespace."""
    return (
        " ".join(text.split())
        .lower()
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )


def is_abstention(answer: str, abstention_message: str) -> bool:
    """Did the model decline to answer?

    Substring rather than equality, because the sentence reliably arrives with
    small decorations ("Unfortunately, I don't have..."). A false NEGATIVE
    here is the expensive direction: an abstention recorded as an answer
    inflates the answered rate, skips escalation, and breaks Phase 4's
    must-abstain assertions — all silently.
    """
    if not answer:
        return False
    needle = _normalize(abstention_message)[:_ABSTENTION_PREFIX_CHARS]
    return needle in _normalize(answer)


class Generator:
    def __init__(
        self,
        llm: LLMClient,
        *,
        abstention_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        self.llm = llm
        self.abstention_message = abstention_message
        # Design.md §7 technique 2: low temperature for factual support
        # answers. Not 0.0 — some open models degenerate into repetition at
        # exactly 0 — but low enough to be effectively deterministic.
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _messages(self, query, citations, results, history):
        return build_messages(
            query, citations, results,
            abstention_message=self.abstention_message,
            history=history,
        )

    async def generate(
        self,
        query: str,
        citations: list[Citation],
        results: list[ScoredChunk],
        history: list[Turn] | None = None,
    ) -> tuple[LLMResponse, int]:
        """Non-streaming generation. Used by the eval harness (Phase 4), where
        streaming buys nothing and complicates concurrency control."""
        started = time.perf_counter()
        response = await self.llm.complete(
            self._messages(query, citations, results, history),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response, int((time.perf_counter() - started) * 1000)

    async def stream(
        self,
        query: str,
        citations: list[Citation],
        results: list[ScoredChunk],
        history: list[Turn] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming generation — the API path.

        Passes the LLM client's events through untouched. Notably it does NOT
        try to strip or rewrite citation markers mid-stream: a marker can be
        split across two deltas ("[" then "1]"), so any mid-stream parsing
        would need a buffer, and buffering defeats the reason to stream.
        Markers reach the client as text and are parsed there and in
        citations.py, both of which see the complete answer.
        """
        async for event in self.llm.stream(
            self._messages(query, citations, results, history),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            yield event
