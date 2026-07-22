"""Content hashing for deduplication (Design.md §3: "Deduplicate (hash check)").

Two levels, for two different jobs:

  DOCUMENT hash -> "have we already ingested this exact content for this
                   tenant?" Backed by UNIQUE(tenant_id, content_hash). A
                   re-crawl that finds nothing changed becomes a no-op, which
                   is what makes event-driven re-ingestion cheap.

  CHUNK hash    -> the embedding cache key, and the way we detect that a
                   document changed but most of its chunks did not (edit one
                   paragraph in a 12-chunk page and 11 embeddings are reused).

Normalization before hashing matters: trailing whitespace or CRLF/LF
differences would otherwise make identical content look changed and trigger
a pointless full re-embed.
"""

from __future__ import annotations

import hashlib
import re

WHITESPACE_RE = re.compile(r"[ \t]+")


def normalize(text: str) -> str:
    """Canonical form for hashing: unix newlines, no trailing spaces, no
    leading/trailing blank lines, collapsed runs of spaces/tabs.

    Deliberately does NOT lowercase or strip punctuation — for a support
    corpus, "ERR_TIMEOUT_502" and "err_timeout_502" are genuinely different
    strings and a case change IS a content change worth re-embedding.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def content_hash(text: str) -> str:
    """sha256 of the normalized text. Full 64 hex chars — truncating invites
    collisions, and the storage cost is trivial."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def embedding_cache_key(model_name: str, text: str) -> str:
    """Key for the embedding_cache table.

    The MODEL NAME is part of the key — embeddings from different models are
    not interchangeable, so a model switch must miss the cache rather than
    silently return vectors from the wrong space (ADR-005).
    """
    return hashlib.sha256(f"{model_name}\x00{normalize(text)}".encode("utf-8")).hexdigest()
