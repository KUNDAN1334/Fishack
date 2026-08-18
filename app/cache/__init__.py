"""Answer caching (Design.md §9).

    Query -> [exact cache] -> miss -> [semantic cache] -> miss
          -> retrieval -> rerank -> generation -> cache the result -> return

Design.md is explicit that this is a COST mechanism first and a latency one
second: "cost < $0.02/query ke liye caching critical hai — cache hit se LLM
call hi skip ho jata hai." A cache hit skips retrieval, reranking AND
generation, which is the entire expensive part of the request.

    keys.py          namespacing, normalization, and the identifier guard
    exact.py         same question -> same answer
    semantic.py      similar question -> same answer (the risky one)
    invalidation.py  a document changed -> which answers are now wrong

Two properties are non-negotiable, and both are about correctness rather than
performance:

TENANT ISOLATION. Every key is namespaced by tenant. A cache is just another
place tenant data lives, and Design.md §9 says so directly: "per-tenant cache
namespace — cache bhi tenant-isolated honi chahiye (same leakage risk
applies!)". Phase 2 spent a whole module making cross-tenant reads
impossible in SQL; serving one from Redis would walk around all of it.

STALENESS. The corpus contains deliberately planted stale-data conflicts
(ADR-009). A cache that keeps serving a pre-update answer recreates exactly
the failure the rest of the system was built to prevent — so invalidation is
active (driven by ingestion), with TTL only as a backstop for bugs in it.
"""
