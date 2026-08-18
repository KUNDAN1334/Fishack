"""Cache key construction, normalization, and the identifier guard.

Small module, three jobs, all of them correctness rather than plumbing.

1. NAMESPACING. Every key starts `fishack:cache:{tenant_id}:`. Not a
   convention — every function here takes tenant_id as its first argument and
   there is no way to build a key without one, the same discipline
   `TenantScope` applies to SQL (ADR-012).

2. NORMALIZATION. "How many retries?" and "how many retries?" are the same
   question. Whitespace and case are folded so trivial variation still hits.
   Punctuation is NOT stripped — see below.

3. THE IDENTIFIER GUARD. Queries containing an error code, version or other
   identifier skip the semantic cache. This is the single most important
   safety mechanism in Phase 5; the reasoning is in `contains_identifier`.
"""

from __future__ import annotations

import hashlib
import re

PREFIX = "fishack:cache"


def _namespace(tenant_id: str) -> str:
    """Every key path begins here. Raises on a missing tenant rather than
    building a global key — a cache entry with no tenant is a leak waiting for
    a lookup."""
    if not tenant_id or not isinstance(tenant_id, str):
        raise ValueError(f"cache keys require a tenant id, got {tenant_id!r}")
    return f"{PREFIX}:{tenant_id}"


def normalize_query(query: str) -> str:
    """Fold trivial variation so it still counts as the same question.

    Case and whitespace only. Punctuation is deliberately KEPT: "ERR_TIMEOUT_502"
    and "ERR TIMEOUT 502" are different strings a user might mean differently,
    and stripping punctuation would also collapse "v2.3" and "v23". The cache
    should be conservative about deciding two questions are identical — a miss
    costs a few cents, a wrong hit costs trust.
    """
    return " ".join(query.split()).lower()


def exact_key(tenant_id: str, query: str) -> str:
    """`fishack:cache:{tenant}:exact:{sha256}`.

    Hashed rather than storing the raw query in the key: queries can be long,
    contain colons (which would break key parsing), and occasionally contain
    things you would rather not have sitting in a Redis keyspace dump.
    """
    digest = hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()
    return f"{_namespace(tenant_id)}:exact:{digest[:32]}"


def semantic_index_key(tenant_id: str) -> str:
    """Sorted set of this tenant's cached entries, scored by insertion time.

    A sorted set rather than a plain set so the semantic cache can scan the
    N most RECENT entries. Recency is the right bound: an answer cached an
    hour ago is more likely to still be valid, and it keeps the linear scan
    cost fixed regardless of how much has ever been cached.
    """
    return f"{_namespace(tenant_id)}:semantic:index"


def semantic_entry_key(tenant_id: str, entry_id: str) -> str:
    """One cached (query embedding + answer) pair."""
    return f"{_namespace(tenant_id)}:semantic:entry:{entry_id}"


def chunk_dependents_key(tenant_id: str, chunk_id: str) -> str:
    """Reverse index: which cache entries were built on this chunk.

    The heart of active invalidation (ADR-025). When a document is re-ingested
    we know its chunk ids; this set turns those into the exact cache keys to
    delete, instead of wiping the tenant's whole cache.
    """
    return f"{_namespace(tenant_id)}:deps:{chunk_id}"


def tenant_pattern(tenant_id: str) -> str:
    """Match everything for one tenant — used by the nuclear invalidation path
    and by tests that assert isolation."""
    return f"{_namespace(tenant_id)}:*"


# ------------------------------------------------------ identifier guard ----

# Patterns that make a query "identifier-bearing". Deliberately broad: a false
# positive costs one cache miss, a false negative can serve the answer for a
# different error code.
_IDENTIFIER_PATTERNS = [
    re.compile(r"\b[A-Z][A-Z0-9]{2,}_[A-Z0-9_]{2,}\b"),   # ERR_TIMEOUT_502
    re.compile(r"\bv\d+\.\d+(\.\d+)?\b", re.IGNORECASE),   # v2.3, v2.3.1
    re.compile(r"\b\d{3}\b"),                              # 502, 429 status codes
    re.compile(r"\b[A-Z]{2,4}-\d{3,}\b"),                  # ACM-1041 ticket ids
    re.compile(r"/[a-z0-9]+/[a-z0-9]+", re.IGNORECASE),    # /v2/export endpoints
]


def contains_identifier(query: str) -> bool:
    """Does this query name something specific? If so, skip the semantic cache.

    THE MOST IMPORTANT FUNCTION IN THE CACHE, and the reason is worth
    understanding properly.

    Embeddings encode meaning, and two error codes MEAN almost the same thing:
    both are "an error code for a failure in this product". So

        "what causes ERR_TIMEOUT_502?"
        "what causes ERR_TIMEOUT_504?"

    embed extremely close together — plausibly above the 0.95 threshold. Their
    correct answers are completely different.

    This is the same weakness that motivated hybrid retrieval in the first
    place (Design.md §5: "vector search error codes ko badly handle karta hai
    kyunki embeddings semantic similarity pe based hain, exact string match pe
    nahi"). The semantic cache is pure vector similarity with no BM25 leg and
    no reranker to correct it — so it inherits that weakness with none of the
    mitigations.

    The exact cache still serves these queries. Only the FUZZY path is
    disabled, which is precisely where the danger is.

    Bias: false positives are cheap (one extra LLM call), false negatives are
    expensive (a confidently wrong answer about a different error code). The
    patterns are broad on purpose.
    """
    return any(pattern.search(query) for pattern in _IDENTIFIER_PATTERNS)
