"""Provider-agnostic LLM client (Design.md: multi-provider resilience).

Layout:
    base.py       - types, errors, the Provider interface
    providers/    - one file per provider, raw httpx, no vendor SDKs
    rate_limit.py - retry/backoff policy (429s, 5xx, timeouts)
    budget.py     - free-quota counters + virtual-cost accounting (Redis)
    client.py     - the fallback chain that ties it all together
"""

from app.llm.base import ChatMessage, LLMResponse, StreamEvent  # noqa: F401
from app.llm.client import LLMClient, build_llm_client  # noqa: F401
