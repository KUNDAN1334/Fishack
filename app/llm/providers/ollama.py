"""Ollama provider — optional local fallback, last in the chain.

Runs a 7-8B model on the developer's own machine: zero quota, full privacy,
but slow on CPU — strictly a "all free APIs are exhausted" safety net,
disabled by default (OLLAMA_ENABLED=false).

Ollama ships an OpenAI-compatible endpoint (/v1/chat/completions), so we
reuse openai_compat.py. Auth: none — Bearer token is sent but ignored.
"""

from app.llm.providers.openai_compat import OpenAICompatProvider


class OllamaProvider(OpenAICompatProvider):
    name = "ollama"

    def __init__(self, *, model: str, base_url: str, enabled: bool, timeout: float = 120.0):
        # timeout=120: CPU inference on an 8B model is legitimately slow;
        # timing out at 60s would waste the work.
        self.enabled = enabled
        super().__init__(model=model, api_key="ollama", base_url=base_url, timeout=timeout)

    def is_configured(self) -> bool:
        # Unlike API providers, "configured" is an explicit opt-in flag, not
        # the presence of a key.
        return self.enabled
