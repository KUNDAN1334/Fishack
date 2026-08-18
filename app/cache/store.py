"""The answer cache: exact match, semantic match, and active invalidation.

One class rather than three files, because the three concerns share the same
Redis connection, the same TTL, and — critically — the same reverse index.
Splitting them would mean three modules all writing to `deps:{chunk_id}`, and
a bug in one of them would be an invalidation hole in another.

Design.md §9's pipeline placement:

    Query -> [exact] -> miss -> [semantic] -> miss -> full pipeline -> store

Exact first because it is a single O(1) GET and cannot be wrong. Semantic only
after it misses, because it costs an embedding plus a scan and CAN be wrong.

THREE RULES THAT ARE ABOUT CORRECTNESS, NOT PERFORMANCE
-------------------------------------------------------

1. Abstentions are never cached. "I don't have enough information" is a
   statement about the corpus at one moment. Cache it and the answer sticks
   for an hour after someone adds the missing documentation — the system would
   actively refuse to use content it now has. The whole point of Phase 1's
   versioning was to stop serving stale information; caching a refusal
   reintroduces it in the worst possible form.

2. Identifier-bearing queries skip the SEMANTIC cache. See
   `keys.contains_identifier`. They still use the exact cache.

3. Every key is tenant-namespaced, and the tenant is a required argument
   everywhere. A cache is another place tenant data lives (Design.md §9).

Every Redis call is wrapped. A cache is an optimization: if Redis is down the
system must get slower, never break. That rule shows up in every method here.
"""

from __future__ import annotations

import json
import logging
import uuid

import redis.asyncio as aioredis

from app.cache import keys as cache_keys
from app.cache.models import CachedAnswer, SemanticEntry

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product — valid as cosine only because the encoder L2-normalizes.
    Same assumption, and the same reason, as `citations.cosine_similarity`."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class AnswerCache:
    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        ttl_seconds: int = 3600,
        semantic_enabled: bool = True,
        semantic_threshold: float = 0.95,
        semantic_max_candidates: int = 200,
        enabled: bool = True,
    ):
        self.redis = redis
        self.ttl = ttl_seconds
        self.semantic_enabled = semantic_enabled
        self.semantic_threshold = semantic_threshold
        self.semantic_max_candidates = semantic_max_candidates
        self.enabled = enabled

    # ------------------------------------------------------------- reads --

    async def get_exact(self, tenant_id: str, query: str) -> CachedAnswer | None:
        """Same question, same answer. One GET, cannot be wrong."""
        if not self.enabled:
            return None
        try:
            raw = await self.redis.get(cache_keys.exact_key(tenant_id, query))
        except Exception:  # noqa: BLE001 — a cache must never break a request
            logger.warning("exact cache read failed", exc_info=True)
            return None
        if not raw:
            return None
        return self._decode(raw)

    async def get_semantic(
        self, tenant_id: str, query: str, query_vector: list[float]
    ) -> CachedAnswer | None:
        """Similar question, same answer. The risky path.

        Guardrail first, work second: an identifier-bearing query returns None
        before we spend anything, because no similarity score should be able
        to override "this query names a specific thing".
        """
        if not self.enabled or not self.semantic_enabled or not query_vector:
            return None

        if cache_keys.contains_identifier(query):
            logger.debug("semantic cache skipped — query names an identifier: %r", query)
            return None

        try:
            # Most recent N entries. Recency-bounded rather than
            # similarity-bounded because a linear scan is the implementation,
            # and it must stay O(constant).
            entry_ids = await self.redis.zrevrange(
                cache_keys.semantic_index_key(tenant_id), 0, self.semantic_max_candidates - 1
            )
            if not entry_ids:
                return None
            raws = await self.redis.mget(
                [cache_keys.semantic_entry_key(tenant_id, _text(eid)) for eid in entry_ids]
            )
        except Exception:  # noqa: BLE001
            logger.warning("semantic cache read failed", exc_info=True)
            return None

        best: tuple[float, CachedAnswer] | None = None
        for raw in raws:
            if not raw:
                continue  # expired between the index read and the mget
            try:
                entry = SemanticEntry.model_validate_json(_text(raw))
            except Exception:  # noqa: BLE001 — a bad entry is not a bad request
                continue
            score = cosine_similarity(query_vector, entry.embedding)
            if score >= self.semantic_threshold and (best is None or score > best[0]):
                best = (score, entry.answer)

        if best is None:
            return None

        score, answer = best
        answer.similarity = score
        # INFO, not debug: a semantic hit means we served an answer written for
        # a different question. That should be visible in logs by default, and
        # the original query is included so a bad hit can be judged by eye.
        logger.info(
            "semantic cache hit (%.4f): %r served the answer for %r",
            score, query, answer.query,
        )
        return answer

    # ------------------------------------------------------------ writes --

    async def store(
        self,
        tenant_id: str,
        query: str,
        answer: CachedAnswer,
        query_vector: list[float] | None = None,
    ) -> None:
        """Cache an answer under both paths, and register its dependencies.

        Refuses to store anything that should not be cached. The refusal lives
        here rather than at the call site so there is exactly one place that
        decides, and a future caller cannot forget.
        """
        if not self.enabled or not answer.answer.strip():
            return

        try:
            pipe = self.redis.pipeline()

            # --- exact path -------------------------------------------------
            exact = cache_keys.exact_key(tenant_id, query)
            pipe.set(exact, answer.model_dump_json(), ex=self.ttl)

            # --- semantic path ----------------------------------------------
            # Skipped for identifier-bearing queries in BOTH directions: we do
            # not read from the semantic cache for them, and we do not pollute
            # it with them either. Storing "what causes ERR_TIMEOUT_502?"
            # would leave a landmine for a later ERR_TIMEOUT_504 query if the
            # read-side guard were ever weakened.
            entry_key = None
            if (
                self.semantic_enabled
                and query_vector
                and not cache_keys.contains_identifier(query)
            ):
                entry_id = uuid.uuid4().hex[:16]
                entry_key = cache_keys.semantic_entry_key(tenant_id, entry_id)
                entry = SemanticEntry(entry_id=entry_id, embedding=query_vector, answer=answer)
                pipe.set(entry_key, entry.model_dump_json(), ex=self.ttl)
                index = cache_keys.semantic_index_key(tenant_id)
                pipe.zadd(index, {entry_id: answer.cached_at.timestamp()})
                pipe.expire(index, self.ttl)
                # Trim the index so it cannot grow without bound. Keeps the
                # scan cheap and stops dead ids accumulating.
                pipe.zremrangebyrank(index, 0, -(self.semantic_max_candidates * 2) - 1)

            # --- reverse index (ADR-025) ------------------------------------
            # For every chunk this answer used, record that these cache keys
            # depend on it. This is what makes precise invalidation possible.
            for chunk_id in answer.chunk_ids:
                deps = cache_keys.chunk_dependents_key(tenant_id, chunk_id)
                pipe.sadd(deps, exact, *( [entry_key] if entry_key else [] ))
                # Dependency sets outlive their entries slightly, so a
                # late-arriving invalidation still finds something to delete.
                pipe.expire(deps, self.ttl * 2)

            await pipe.execute()
        except Exception:  # noqa: BLE001
            logger.warning("cache write failed (ignored)", exc_info=True)

    # ------------------------------------------------------ invalidation --

    async def invalidate_chunks(self, tenant_id: str, chunk_ids: list[str]) -> int:
        """Delete every cached answer built on any of these chunks.

        Called by ingestion when a document is re-ingested or superseded
        (ADR-025). Returns how many cache keys were removed.

        This is the mechanism Design.md §9 asks for by name — "active
        invalidation on ingestion of new/updated docs (invalidate cache
        entries linked to updated source_ids)". TTL alone would serve a stale
        answer for up to an hour after a correction shipped, which is the
        exact failure the corpus's planted conflicts exist to test.
        """
        if not self.enabled or not chunk_ids:
            return 0
        try:
            dep_keys = [cache_keys.chunk_dependents_key(tenant_id, cid) for cid in chunk_ids]
            # One round trip to collect every dependent key.
            pipe = self.redis.pipeline()
            for key in dep_keys:
                pipe.smembers(key)
            results = await pipe.execute()

            doomed: set[str] = set()
            for members in results:
                doomed.update(_text(m) for m in members)

            if not doomed and not dep_keys:
                return 0

            pipe = self.redis.pipeline()
            if doomed:
                pipe.delete(*doomed)
            pipe.delete(*dep_keys)   # the dependency sets themselves
            await pipe.execute()

            if doomed:
                logger.info(
                    "invalidated %d cached answer(s) for tenant %s across %d chunk(s)",
                    len(doomed), tenant_id, len(chunk_ids),
                )
            return len(doomed)
        except Exception:  # noqa: BLE001
            # A failed invalidation is the one cache error with a real cost:
            # stale answers survive until TTL. Logged at WARNING so it is
            # visible, but still not allowed to fail the ingest.
            logger.warning("cache invalidation failed for tenant %s", tenant_id, exc_info=True)
            return 0

    async def invalidate_tenant(self, tenant_id: str) -> int:
        """Nuke one tenant's whole cache. The blunt instrument.

        Used by the CLI and by tests. Not the ingestion path — that uses the
        precise version. `scan_iter` rather than `KEYS` because `KEYS` blocks
        the Redis event loop, which is fine on a laptop and an outage in
        production.
        """
        if not self.enabled:
            return 0
        deleted = 0
        try:
            async for key in self.redis.scan_iter(match=cache_keys.tenant_pattern(tenant_id)):
                await self.redis.delete(key)
                deleted += 1
        except Exception:  # noqa: BLE001
            logger.warning("tenant cache flush failed", exc_info=True)
        return deleted

    # ---------------------------------------------------------- internals --

    @staticmethod
    def _decode(raw) -> CachedAnswer | None:
        try:
            return CachedAnswer.model_validate_json(_text(raw))
        except Exception:  # noqa: BLE001 — a corrupt entry is a miss, not a crash
            logger.warning("could not decode cached answer; treating as a miss")
            return None


def _text(value) -> str:
    """redis-py returns bytes unless decode_responses=True. Handle both, so
    the cache works regardless of how the client was constructed."""
    return value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else value


def summarize_for_cache(response, query: str) -> CachedAnswer:
    """Turn a ChatResponse into the smaller thing we store.

    Deliberately drops the retrieval result and all per-request timing. See
    `app/cache/models.py` for why replaying those numbers would corrupt
    /stats.
    """
    return CachedAnswer(
        query=query,
        answer=response.answer,
        citations=response.citations,
        citation_report=response.citation_report,
        confidence=response.confidence,
        chunk_ids=[citation.chunk_id for citation in response.citations],
        provider=response.provider,
        model=response.model,
        original_cost_usd=response.virtual_cost_usd,
    )
