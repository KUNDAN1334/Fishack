"""Cache-backed embedding service.

"Cache all embeddings (they're deterministic — never embed the same text
twice)." The embedding_cache table is keyed by sha256(model || normalized
text), so:

  - re-ingesting an unchanged doc costs zero model compute
  - the SAME text appearing under two tenants is embedded once (the vector
    is tenant-independent; only the CHUNK ROW is tenant-scoped, so this is
    safe — see interview_prep Q on why this isn't a leak)
  - switching models misses the entire cache by construction, rather than
    silently mixing vector spaces

Flow: look up all keys in one query -> encode only the misses -> write the
new vectors back -> return vectors in the caller's original order.
"""

from __future__ import annotations

import logging

import asyncpg

from app.embeddings.encoder import Encoder
from app.ingestion.dedup import embedding_cache_key

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, pool: asyncpg.Pool, encoder: Encoder):
        self.pool = pool
        self.encoder = encoder
        self.stats = {"hits": 0, "misses": 0}

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk texts, using the DB cache. Order is preserved."""
        if not texts:
            return []

        keys = [embedding_cache_key(self.encoder.model_name, text) for text in texts]
        cached = await self._fetch_cached(keys)

        # Encode only the misses, and only once per distinct key: a batch
        # containing the same text twice must not encode it twice.
        missing_indices = [i for i, key in enumerate(keys) if key not in cached]
        distinct_missing: dict[str, str] = {}
        for i in missing_indices:
            distinct_missing.setdefault(keys[i], texts[i])

        if distinct_missing:
            missing_keys = list(distinct_missing)
            vectors = self.encoder.encode_passages([distinct_missing[k] for k in missing_keys])
            new_entries = dict(zip(missing_keys, vectors))
            await self._store_cached(new_entries)
            cached.update(new_entries)

        self.stats["hits"] += len(texts) - len(missing_indices)
        self.stats["misses"] += len(missing_indices)
        return [cached[key] for key in keys]

    async def embed_query(self, text: str) -> list[float]:
        """Query embeddings are NOT cached here.

        Two reasons: they use a different (instruction-prefixed) input, and
        query caching is the job of the semantic cache in Phase 5, which
        needs the vector anyway to do its similarity comparison.
        """
        return self.encoder.encode_query(text)

    # ------------------------------------------------------------ internals --

    async def _fetch_cached(self, keys: list[str]) -> dict[str, list[float]]:
        """One query for all keys — N round trips would dominate runtime."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT cache_key, embedding FROM embedding_cache WHERE cache_key = ANY($1::text[])",
                list(set(keys)),
            )
        # pgvector returns the vector as a string like "[0.1,0.2,...]" over
        # the wire unless a codec is registered; parse defensively so this
        # works with or without one.
        return {row["cache_key"]: _parse_vector(row["embedding"]) for row in rows}

    async def _store_cached(self, entries: dict[str, list[float]]) -> None:
        """ON CONFLICT DO NOTHING: two concurrent ingest runs embedding the
        same text is a race we can simply ignore — the vectors are identical."""
        if not entries:
            return
        records = [
            (key, self.encoder.model_name, _format_vector(vector))
            for key, vector in entries.items()
        ]
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO embedding_cache (cache_key, model, embedding)
                VALUES ($1, $2, $3::vector)
                ON CONFLICT (cache_key) DO NOTHING
                """,
                records,
            )


def _format_vector(vector: list[float]) -> str:
    """Python list -> pgvector literal."""
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def _parse_vector(value) -> list[float]:
    if isinstance(value, str):
        return [float(part) for part in value.strip("[]").split(",") if part]
    return list(value)
