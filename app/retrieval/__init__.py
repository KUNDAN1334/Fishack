"""Hybrid retrieval (Design.md §5, §6, §8).

Two legs — BM25 over Postgres full-text search and cosine similarity over
pgvector — merged by Reciprocal Rank Fusion, then optionally reordered by a
local cross-encoder. Every query goes through a `TenantScope`, which is the
only object in the codebase permitted to read the `chunks` table.

Import order if you're reading this package cold (dependencies first):

    models.py        the vocabulary everything else speaks
    tenant_scope.py  isolation enforcement — read this before any leg
    bm25.py          keyword leg
    vector.py        semantic leg
    fusion.py        pure RRF; no DB, no models, no I/O
    conditional.py   pure "is this ambiguous enough to rerank?" rule
    reranker.py      cross-encoder wrapper
    service.py       the orchestrator that ties the above together
"""
