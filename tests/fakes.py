"""Test doubles for the LLM layer.

FakeProvider is scripted with a list of behaviors, one per call:
  "ok"         -> return a canned response
  "rate_limit" -> raise RateLimitError
  "transient"  -> raise TransientError
  "auth"       -> raise AuthError
The last behavior repeats if called more times than scripted — so
["rate_limit"] means "always rate-limited".
"""

from typing import AsyncIterator

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
