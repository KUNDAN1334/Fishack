"""Groq provider — primary in the fallback chain.

Why primary: fastest inference (custom LPU hardware) and the most generous
free request quota, which matters because the confidence gate means many
requests never reach generation at all, but rewriting + generation for the
rest should be snappy.

Groq exposes an OpenAI-compatible endpoint, so all the work lives in
openai_compat.py.
"""

from app.llm.providers.openai_compat import OpenAICompatProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAICompatProvider):
    name = "groq"

    def __init__(self, *, model: str, api_key: str, timeout: float = 60.0):
        super().__init__(model=model, api_key=api_key, base_url=GROQ_BASE_URL, timeout=timeout)
