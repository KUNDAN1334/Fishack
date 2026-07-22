"""Token counting for chunk sizing.

Why this is not `len(text.split())`: chunk budgets (300-500 tokens) only
mean something if they're measured with the SAME tokenizer the embedding
model uses. bge-small truncates at 512 tokens — a chunk that's "450 tokens"
by word count could be 700 real tokens and get silently truncated, losing
the tail of the text from the embedding while it still appears in the DB.
Silent truncation is the nastiest ingestion bug there is.

Two implementations behind one protocol:
  HFTokenCounter     - the real bge tokenizer (used in the pipeline)
  ApproxTokenCounter - chars/4 heuristic (used in tests, keeps the test
                       suite free of a torch dependency)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

logger = logging.getLogger(__name__)


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class ApproxTokenCounter:
    """~4 characters per token for English. Deterministic, dependency-free.

    Used in tests and as a fallback if transformers isn't installed. Fine for
    chunk-boundary decisions (it errs within ~15%), NOT for anything that
    must respect a hard model limit.
    """

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class HFTokenCounter:
    """Wraps the embedding model's own HuggingFace tokenizer."""

    def __init__(self, model_name: str):
        from transformers import AutoTokenizer  # imported lazily: heavy dep

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(self, text: str) -> int:
        # add_special_tokens=False: we're measuring content, not a model
        # input. The 2 special tokens are accounted for by MAX_MODEL_TOKENS
        # having headroom below the model's real 512 limit.
        return len(self.tokenizer.encode(text, add_special_tokens=False))


@lru_cache
def get_token_counter(model_name: str) -> TokenCounter:
    """Real tokenizer if transformers is available, approximation otherwise.

    Cached because loading a tokenizer takes ~1s and ingestion calls this
    once per chunk boundary decision.
    """
    try:
        return HFTokenCounter(model_name)
    except Exception as exc:  # noqa: BLE001 — any import/download failure
        logger.warning(
            "falling back to approximate token counting (%s). Chunk sizes will "
            "be within ~15%% of true token counts.", exc,
        )
        return ApproxTokenCounter()
