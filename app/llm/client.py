"""The fallback chain: one LLMClient facade over an ordered list of
providers.

This is the multi-provider resilience pattern from production systems: any
single provider WILL rate-limit or go down; the caller should never notice.
Free-tier quotas just make it fire more often — which is why we treat it as
a feature, not a workaround.

Flow for complete():
    for each configured provider in order:
        retry it patiently (rate_limit.call_with_retries: backoff + jitter)
        success -> record budget, attach failover history, return
        exhausted/auth-failed -> log a failover event, try next provider
    all failed -> AllProvidersFailedError (caller decides: 503 / abstain)

Streaming is subtly different — see stream() for why failover only happens
BEFORE the first token.
"""

import datetime as dt
import logging
import time
from typing import AsyncIterator

from app.config import Settings
from app.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    ProviderError,
    StreamEvent,
)
from app.llm.budget import BudgetTracker
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openrouter import OpenRouterProvider
from app.llm.rate_limit import RetryPolicy, call_with_retries

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """Every provider in the chain was tried and failed."""

    def __init__(self, failover_events: list[dict]):
        self.failover_events = failover_events
        tried = ", ".join(e["provider"] for e in failover_events) or "none"
        super().__init__(f"all LLM providers failed (tried: {tried})")


def _failover_event(provider: str, exc: Exception) -> dict:
    """Structured record of one failed provider — stored in
    traces.failover_events so outages are visible in observability, not just
    in logs."""
    return {
        "provider": provider,
        "error_type": type(exc).__name__,
        "error": str(exc)[:300],
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


class LLMClient:
    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        budget: BudgetTracker | None = None,
        retry_policy: RetryPolicy | None = None,
        default_temperature: float = 0.1,
        default_max_tokens: int = 1024,
    ):
        # Only configured providers make it into the chain; an empty chain
        # is a config error we surface immediately, not at first request.
        self.providers = [p for p in providers if p.is_configured()]
        if not self.providers:
            raise ValueError(
                "No LLM providers configured. Set at least one API key "
                "(GROQ_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY) or "
                "OLLAMA_ENABLED=true. See .env.example."
            )
        self.budget = budget
        self.retry_policy = retry_policy or RetryPolicy()
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

    # ------------------------------------------------------------ helpers --

    async def _record_budget(self, response: LLMResponse) -> None:
        """Best-effort: an answer must never fail because a counter did."""
        if self.budget is None:
            return
        try:
            response.virtual_cost_usd = await self.budget.record(
                response.provider, response.model, response.usage
            )
        except Exception:  # noqa: BLE001 — deliberately broad, see docstring
            logger.exception("budget tracking failed (ignored)")

    # ----------------------------------------------------------- complete --

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        failover_events: list[dict] = []
        for provider in self.providers:
            try:
                response = await call_with_retries(
                    # Bind loop variable explicitly (p=provider) — a bare
                    # lambda would capture the variable, not the value
                    lambda p=provider: p.complete(
                        messages, temperature=temperature, max_tokens=max_tokens
                    ),
                    self.retry_policy,
                )
            except ProviderError as exc:
                failover_events.append(_failover_event(provider.name, exc))
                logger.warning("failing over from %s: %s", provider.name, exc)
                continue
            response.failover_events = failover_events
            await self._record_budget(response)
            return response
        raise AllProvidersFailedError(failover_events)

    # ------------------------------------------------------------- stream --

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming with failover — but ONLY before the first token.

        Once deltas have been yielded, the user has seen partial text; a
        silent retry on another provider would restart the answer (possibly
        worded differently) mid-message. Correctness > cleverness: after
        first token, errors propagate and the API layer shows a clean
        "generation interrupted" state.

        Also no call_with_retries wrapper here: with 4 providers behind us,
        failing over immediately beats making the user wait through backoff
        sleeps before their first token.
        """
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        failover_events: list[dict] = []
        for provider in self.providers:
            started_streaming = False
            try:
                async for event in provider.stream(
                    messages, temperature=temperature, max_tokens=max_tokens
                ):
                    if event.type == "delta":
                        started_streaming = True
                        yield event
                    elif event.type == "done":
                        assert event.response is not None
                        event.response.failover_events = failover_events
                        await self._record_budget(event.response)
                        yield event
                return
            except ProviderError as exc:
                if started_streaming:
                    raise  # see docstring: no mid-answer provider swaps
                failover_events.append(_failover_event(provider.name, exc))
                logger.warning("failing over from %s (pre-token): %s", provider.name, exc)
                continue
        raise AllProvidersFailedError(failover_events)


# -------------------------------------------------------------- factory ----


def build_providers(settings: Settings) -> list[LLMProvider]:
    """Instantiate providers in the configured chain order. Unknown names in
    LLM_PROVIDER_ORDER fail loudly — a typo silently shortening the chain
    would be a nasty production surprise."""
    registry = {
        "groq": lambda: GroqProvider(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            timeout=settings.llm_timeout_seconds,
        ),
        "gemini": lambda: GeminiProvider(
            model=settings.gemini_model,
            api_key=settings.google_api_key,
            timeout=settings.llm_timeout_seconds,
        ),
        "openrouter": lambda: OpenRouterProvider(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            timeout=settings.llm_timeout_seconds,
        ),
        "ollama": lambda: OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            enabled=settings.ollama_enabled,
        ),
    }
    providers = []
    for name in settings.provider_order:
        if name not in registry:
            raise ValueError(f"Unknown provider '{name}' in LLM_PROVIDER_ORDER")
        providers.append(registry[name]())
    return providers


def build_llm_client(settings: Settings, budget: BudgetTracker | None = None) -> LLMClient:
    return LLMClient(
        build_providers(settings),
        budget=budget,
        retry_policy=RetryPolicy(
            max_attempts=settings.retry_max_attempts,
            base_delay=settings.retry_base_delay,
            max_delay=settings.retry_max_delay,
        ),
        default_temperature=settings.llm_temperature,
        default_max_tokens=settings.llm_max_tokens,
    )
