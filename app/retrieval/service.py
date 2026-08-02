"""The retrieval pipeline (Design.md §5 step 5, §6 step 6).

    query
      -> embed once (BGE query instruction prefix)
      -> BM25 leg  ┐
      -> vector leg┘ concurrently, both tenant-scoped
      -> Reciprocal Rank Fusion -> top-20 candidates
      -> conditional gate: is this ambiguous enough to rerank?
      -> cross-encoder rerank -> top-5
      -> RetrievalResult (results + full candidates + per-stage timings)

Three deliberate choices worth understanding before reading the code:

1. ONE code path for all three modes. `mode="bm25"` and `mode="vector"` run
   through this same function with one leg disabled, rather than through
   separate shortcut functions. Phase 4's headline table compares BM25-only
   vs vector-only vs hybrid; if the single-leg arms went through different
   code, the table would be comparing implementations, not retrieval
   strategies. This is the difference between an eval and a demo.

2. FUSION OVER ROWS WE ALREADY HAVE. The legs return full chunk rows, so
   fusing produces a set union of objects already in memory — no "hydrate the
   winning ids" round trip. The naive pipeline fetches ids, fuses, then
   SELECTs the survivors; that is one extra round trip per query to retrieve
   data it just threw away.

3. A DEAD LEG DEGRADES, IT DOES NOT KILL. If BM25 throws, hybrid retrieval
   quietly becomes vector-only and says so in `degraded_legs`. Answering from
   one leg is worse than answering from two and much better than a 500. Both
   legs failing is a real error and raises.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.embeddings.service import EmbeddingService
from app.retrieval import bm25 as bm25_leg
from app.retrieval import vector as vector_leg
from app.retrieval.conditional import should_rerank
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import (
    LEG_BM25,
    LEG_VECTOR,
    LegResult,
    RetrievalMode,
    RetrievalResult,
    RetrievedChunk,
    ScoredChunk,
)
from app.retrieval.reranker import Reranker, rerank_candidates
from app.retrieval.tenant_scope import TenantScope

logger = logging.getLogger(__name__)


class AllLegsFailedError(RuntimeError):
    """Every retrieval leg failed. Phase 3 turns this into an abstention —
    never into a generated answer, because there is no context to ground one
    in (Design.md §7: closed-book means no context = no answer)."""


class RetrievalService:
    """Runs the pipeline for one tenant scope at a time.

    Note the constructor takes no tenant id: tenancy arrives with each call as
    a `TenantScope`, so this object can be built once at app startup and
    shared. There is deliberately no `self.tenant_id` that a method could
    forget to use.
    """

    def __init__(
        self,
        embeddings: EmbeddingService,
        settings: Settings,
        reranker: Reranker | None = None,
    ):
        self.embeddings = embeddings
        self.settings = settings
        # None means "no reranker available" (not configured, or a caller that
        # explicitly does not want one, e.g. the Phase 4 no-rerank eval arm).
        # Distinct from `settings.reranker_enabled=False`, which is a config
        # decision — both end up skipping, with different reason codes.
        self.reranker = reranker

    async def retrieve(
        self,
        scope: TenantScope,
        query: str,
        *,
        mode: RetrievalMode = "hybrid",
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Retrieve the best chunks for `query` within `scope`."""
        started = time.perf_counter()
        settings = self.settings
        top_k = top_k or settings.rerank_top_k

        result = RetrievalResult(query=query, tenant_id=scope.tenant_id, mode=mode)

        # ---------------------------------------------------- 1. embed --
        # Done once, before the legs, because the vector leg needs it and
        # Phase 5's semantic cache will reuse the same vector. Only skipped
        # for BM25-only mode, where paying ~15ms of CPU for an unused vector
        # would quietly distort the Phase 4 latency comparison.
        query_vector: list[float] = []
        if mode in ("vector", "hybrid"):
            embed_started = time.perf_counter()
            query_vector = await self.embeddings.embed_query(query)
            result.embed_ms = int((time.perf_counter() - embed_started) * 1000)

        # ------------------------------------------- 2. run the legs --
        retrieval_started = time.perf_counter()
        leg_results, chunks = await self._run_legs(scope, query, query_vector, mode)
        result.legs = leg_results
        result.retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

        healthy = [leg for leg in leg_results if leg.ok]
        result.degraded_legs = [leg.leg for leg in leg_results if not leg.ok]
        if not healthy:
            # Both legs down means the database is unreachable or the schema
            # is wrong — not "no results". Those must not look the same.
            raise AllLegsFailedError(
                f"all retrieval legs failed for tenant {scope.tenant_id}: "
                + "; ".join(f"{leg.leg}: {leg.error}" for leg in leg_results)
            )
        if result.degraded_legs:
            logger.warning(
                "retrieval degraded for tenant %s: legs %s failed, answering from %s",
                scope.tenant_id, result.degraded_legs, [leg.leg for leg in healthy],
            )

        # ------------------------------------------------------ 3. fuse --
        candidates = self._fuse(healthy, chunks)
        result.candidates = candidates

        if not candidates:
            # An empty corpus, or a query matching nothing in either leg.
            # Legitimate and common (out-of-scope questions), so it returns an
            # empty result rather than raising — Phase 3's confidence gate
            # sees top_score == 0.0 and abstains, which is the correct answer.
            result.total_ms = int((time.perf_counter() - started) * 1000)
            logger.info("no candidates for query %r (tenant %s)", query, scope.tenant_id)
            return result

        # ------------------------------------- 4. gate + 5. rerank --
        decision = should_rerank(
            [candidate.fused_score for candidate in candidates],
            reranker_enabled=settings.reranker_enabled and self.reranker is not None,
            gate_enabled=settings.conditional_rerank_enabled,
            window=settings.rerank_ambiguity_window,
            threshold=settings.rerank_margin_threshold,
        )
        result.rerank = decision

        if decision.reranked and self.reranker is not None:
            # Only the top slice of the fused list reaches the cross-encoder.
            # Reranking cost is linear in pairs and measured at ~270ms/pair on
            # a laptop CPU, so this is the difference between a usable
            # time-to-first-token and an unusable one. Retrieval is unaffected
            # — `result.candidates` still holds the full fused list, which is
            # what Phase 4's recall@20 is computed over.
            rerank_input = candidates[: settings.rerank_input_top_k]

            # Reranking is CPU-bound and synchronous (a torch forward pass).
            # Running it directly in the event loop would block every other
            # request for its whole duration, so it goes to a thread.
            # PRODUCTION NOTE: at real concurrency this belongs in a separate
            # model-serving process (TorchServe / Triton / a hosted reranker),
            # not a thread in the API process — the GIL makes threads a
            # latency fix, not a throughput one.
            reranked, rerank_ms = await asyncio.to_thread(
                rerank_candidates,
                self.reranker,
                query,
                rerank_input,
                top_k=top_k,
                max_length=settings.reranker_max_length,
            )
            result.results = reranked
            result.rerank_ms = rerank_ms
            result.reranked_candidates = len(rerank_input)
        else:
            # No rerank: fusion order is the final order.
            result.results = candidates[:top_k]

        result.total_ms = int((time.perf_counter() - started) * 1000)
        return result

    # ----------------------------------------------------------- internals --

    async def _run_legs(
        self,
        scope: TenantScope,
        query: str,
        query_vector: list[float],
        mode: RetrievalMode,
    ) -> tuple[list[LegResult], dict[str, RetrievedChunk]]:
        """Run the enabled legs concurrently and merge their chunk maps.

        `asyncio.gather` here is a real win, not decoration: the two legs hit
        different indexes (GIN and HNSW) on separate pooled connections, so
        hybrid retrieval costs roughly max(bm25, vector) instead of their sum.
        """
        limit = self.settings.retrieval_candidates_per_leg
        tasks = []

        if mode in ("bm25", "hybrid"):
            tasks.append(bm25_leg.search_bm25(scope, query, limit))
        if mode in ("vector", "hybrid"):
            tasks.append(
                vector_leg.search_vector(scope, query_vector, limit, self.settings.hnsw_ef_search)
            )

        outputs = await asyncio.gather(*tasks)

        leg_results: list[LegResult] = []
        chunks: dict[str, RetrievedChunk] = {}
        for leg_result, leg_chunks in outputs:
            leg_results.append(leg_result)
            # Both legs can return the same chunk; the objects are identical
            # (same row, same mapping), so last-write-wins is safe.
            chunks.update(leg_chunks)
        return leg_results, chunks

    def _fuse(
        self, healthy_legs: list[LegResult], chunks: dict[str, RetrievedChunk]
    ) -> list[ScoredChunk]:
        """RRF over the healthy legs, then attach per-leg evidence.

        Only healthy legs are fused. Including a failed leg's empty list would
        be harmless arithmetically (it contributes nothing) but would make the
        `ranks` evidence in the playground read as "vector found nothing",
        which is a different and misleading statement from "vector errored".
        """
        ranked_lists = {leg.leg: leg.chunk_ids for leg in healthy_legs}
        weights = {
            LEG_BM25: self.settings.rrf_weight_bm25,
            LEG_VECTOR: self.settings.rrf_weight_vector,
        }
        by_leg = {leg.leg: leg for leg in healthy_legs}

        fused = reciprocal_rank_fusion(
            ranked_lists,
            k=self.settings.rrf_k,
            weights=weights,
            top_k=self.settings.retrieval_fusion_top_k,
        )

        scored: list[ScoredChunk] = []
        for position, candidate in enumerate(fused, start=1):
            chunk = chunks.get(candidate.chunk_id)
            if chunk is None:
                # Cannot happen: every fused id came from a leg that also
                # returned its row. Guard anyway — a silent KeyError here
                # would be reported as "retrieval returns fewer results than
                # expected", which is a miserable thing to debug.
                logger.error("fused id %s has no chunk row; skipping", candidate.chunk_id)
                continue

            item = ScoredChunk(
                chunk=chunk,
                fused_score=candidate.score,
                fused_rank=position,
            )
            if LEG_BM25 in candidate.ranks:
                item.bm25_rank = candidate.ranks[LEG_BM25]
                item.bm25_score = by_leg[LEG_BM25].scores.get(candidate.chunk_id)
            if LEG_VECTOR in candidate.ranks:
                item.vector_rank = candidate.ranks[LEG_VECTOR]
                item.vector_score = by_leg[LEG_VECTOR].scores.get(candidate.chunk_id)
            scored.append(item)
        return scored


def build_retrieval_service(
    embeddings: EmbeddingService,
    settings: Settings,
    *,
    with_reranker: bool = True,
) -> RetrievalService:
    """Factory used by the API, the playground, and the eval harness.

    `with_reranker=False` skips loading a 280MB model — worth it for callers
    that only measure first-stage retrieval (Phase 4's no-rerank arm) and for
    fast iteration in the playground.
    """
    reranker = None
    if with_reranker and settings.reranker_enabled:
        # Imported lazily so that constructing a no-reranker service never
        # pulls torch into the process.
        from app.retrieval.reranker import get_reranker

        reranker = get_reranker(
            settings.reranker_model_name,
            settings.reranker_batch_size,
            settings.reranker_max_length,
        )
    return RetrievalService(embeddings, settings, reranker=reranker)
