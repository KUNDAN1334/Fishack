"""Local embedding generation (Design.md §5).

    encoder.py  sentence-transformers wrapper (bge-small, CPU)
    service.py  cache-backed embedding: check embedding_cache, encode misses

Free and deterministic by design — the same text always yields the same
vector, which is precisely what makes caching correct rather than merely an
optimization.
"""
