"""OpenRouter provider — third in the fallback chain.

OpenRouter aggregates many hosts behind one OpenAI-compatible API; ':free'
model variants cost nothing (~20 req/min, ~50-200 req/day). Good breadth,
strictest limits — hence third.
"""

from app.llm.providers.openai_compat import OpenAICompatProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"

    def __init__(self, *, model: str, api_key: str, timeout: float = 60.0):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
            # Optional attribution headers OpenRouter asks apps to send
            extra_headers={"HTTP-Referer": "https://github.com/fishack", "X-Title": "Fishack"},
        )
