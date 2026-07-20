"""Shared types, errors, and the Provider interface for the LLM layer.

Every provider (Groq, Gemini, OpenRouter, Ollama) speaks a different HTTP
dialect; this module defines the ONE shape the rest of Fishly sees. Nothing
outside app/llm/ ever touches a provider-specific field.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    # True when the provider didn't report usage (some streaming responses)
    # and we fell back to a chars/4 heuristic — flagged so virtual-cost
    # numbers built on it are known to be approximate.
    estimated: bool = False


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0
    # Populated by LLMClient when earlier providers in the chain failed —
    # lands in traces.failover_events for observability.
    failover_events: list[dict] = Field(default_factory=list)
    virtual_cost_usd: float = 0.0


class StreamEvent(BaseModel):
    """One event from a streaming generation.

    type='delta': `text` is the next fragment of the answer.
    type='done':  `response` carries the complete LLMResponse (full text,
                  usage, latency) — callers use it for tracing/budget.
    """

    type: Literal["delta", "done"]
    text: str = ""
    response: LLMResponse | None = None


# ----------------------------------------------------------------- errors --
# Explicit error taxonomy so the retry layer and the fallback chain can make
# different decisions per class:
#   RateLimitError  -> retry with backoff, then fail over
#   TransientError  -> retry with backoff, then fail over (5xx, timeouts)
#   AuthError       -> fail over IMMEDIATELY (retrying a bad key is pointless)
#   ProviderError   -> catch-all; fail over without retries


class ProviderError(Exception):
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class RateLimitError(ProviderError):
    def __init__(self, provider: str, message: str, retry_after: float | None = None):
        # Seconds the provider asked us to wait (Retry-After header), if given
        self.retry_after = retry_after
        super().__init__(provider, message)


class AuthError(ProviderError):
    pass


class TransientError(ProviderError):
    pass


class LLMProvider(ABC):
    """Interface every provider implements. Constructor args differ; the
    call surface does not."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this provider has what it needs (API key / enabled flag).
        Unconfigured providers are skipped when building the chain."""

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Single non-streaming completion."""

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming completion: yields deltas, ends with a 'done' event."""


def estimate_tokens(text: str) -> int:
    """Crude fallback when a provider omits usage: ~4 chars/token for
    English. Only used to keep virtual-cost tracking non-zero; flagged via
    TokenUsage.estimated."""
    return max(1, len(text) // 4)
