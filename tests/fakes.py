"""Test doubles.

LLM layer — FakeProvider is scripted with a list of behaviors, one per call:
  "ok"         -> return a canned response
  "rate_limit" -> raise RateLimitError
  "transient"  -> raise TransientError
  "auth"       -> raise AuthError
The last behavior repeats if called more times than scripted — so
["rate_limit"] means "always rate-limited".

Retrieval layer (Phase 2) — FakeEncoder and FakeReranker exist so the test
suite never imports torch. That is not just about speed: a suite that needs a
280MB model download cannot run in CI on every push, and the tenant-leakage
test is exactly the test you want running on every push.
"""

import hashlib
import math
import random
from typing import AsyncIterator, Sequence

from app.llm.base import (
    AuthError,
    ChatMessage,
    LLMProvider,
    LLMResponse,
    RateLimitError,
    StreamEvent,
    TokenUsage,
    TransientError,
)


class FakeProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        behaviors: list[str],
        *,
        text: str = "fake answer",
        retry_after: float | None = None,
        configured: bool = True,
    ):
        self.name = name
        self.behaviors = behaviors
        self.text = text
        self.retry_after = retry_after
        self.configured = configured
        self.calls = 0  # assert retry counts in tests

    def is_configured(self) -> bool:
        return self.configured

    def _next_behavior(self) -> str:
        behavior = self.behaviors[min(self.calls, len(self.behaviors) - 1)]
        self.calls += 1
        return behavior

    def _maybe_raise(self) -> None:
        behavior = self._next_behavior()
        if behavior == "rate_limit":
            raise RateLimitError(self.name, "scripted 429", retry_after=self.retry_after)
        if behavior == "transient":
            raise TransientError(self.name, "scripted 503")
        if behavior == "auth":
            raise AuthError(self.name, "scripted 401")
        assert behavior == "ok", f"unknown scripted behavior: {behavior}"

    def _response(self) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            provider=self.name,
            model=f"{self.name}-model",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
        )

    async def complete(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        self._maybe_raise()
        return self._response()

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        self._maybe_raise()
        for word in self.text.split():
            yield StreamEvent(type="delta", text=word + " ")
        yield StreamEvent(type="done", response=self._response())


class MidStreamFailProvider(FakeProvider):
    """Yields one delta, then dies — exercises the 'no failover after first
    token' rule."""

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        yield StreamEvent(type="delta", text="partial ")
        raise TransientError(self.name, "died mid-stream")


# ------------------------------------------------------ retrieval doubles --


class FakeEncoder:
    """Deterministic 384-dim vectors derived from a hash of the text.

    What this IS good for: exercising the vector leg's SQL — pgvector
    round-trips, the `<=>` operator, HNSW index usage, the tenant filter,
    result shape. Identical text reliably produces an identical vector, so
    "does the query vector match the stored chunk vector" is testable.

    What this is NOT: semantic. Two paraphrases hash to unrelated vectors, so
    no test may use this to claim "the vector leg finds paraphrases BM25
    misses". That claim is a QUALITY claim, and quality is measured by the
    Phase 4 eval harness against real embeddings — not asserted in a unit
    test with fake ones. Conflating the two is how a green suite ends up
    hiding a broken retriever.
    """

    model_name = "fake-encoder-384"
    dimension = 384

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        values = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        # L2-normalize, matching the real encoder — the vector leg's
        # `1 - (a <=> b)` = cosine similarity identity depends on it.
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def encode_query(self, text: str) -> list[float]:
        # The real encoder prefixes queries with a BGE instruction; mirroring
        # that here keeps query and passage vectors distinct, as they are in
        # production.
        return self._vector("query: " + text)


class FakeReranker:
    """Scores by keyword presence, so tests can state intent readably.

    `scores_by_keyword` maps a substring to the logit a passage containing it
    receives. Passages matching nothing get `default`.
    """

    def __init__(self, scores_by_keyword: dict[str, float] | None = None, default: float = 0.0):
        self.scores_by_keyword = scores_by_keyword or {}
        self.default = default
        self.calls = 0

    def score_pairs(self, query: str, passages: Sequence[str]) -> list[float]:
        self.calls += 1
        scores = []
        for passage in passages:
            score = self.default
            for keyword, value in self.scores_by_keyword.items():
                if keyword.lower() in passage.lower():
                    score = value
                    break
            scores.append(score)
        return scores
