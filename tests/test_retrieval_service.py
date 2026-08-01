"""RetrievalService orchestration, with the legs stubbed out.

The legs are tested against a real database (test_retrieval_sql.py) and
isolation end-to-end (test_tenant_isolation.py) — both of which skip when
Docker is down. The ORCHESTRATION logic, though, is pure decision-making:
which legs run for which mode, what happens when one dies, how per-leg
evidence gets attached to fused candidates. None of that needs Postgres, and
all of it should run on every push.

So we monkeypatch the two leg functions and assert the pipeline's behavior.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.config import Settings
from app.retrieval import bm25 as bm25_module
from app.retrieval import service as service_module
from app.retrieval import vector as vector_module
from app.retrieval.models import LEG_BM25, LEG_VECTOR, LegResult, RetrievedChunk
from app.retrieval.service import AllLegsFailedError, RetrievalService
from app.retrieval.tenant_scope import TenantScope
from tests.fakes import FakeReranker


class StubEmbeddings:
    def __init__(self):
        self.query_calls = 0

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return [0.1] * 384


def make_chunk(chunk_id: str, content: str = "body") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        tenant_id="acme",
        content=content,
        effective_date=dt.date(2026, 6, 1),
    )


def stub_leg(leg_name: str, chunk_ids: list[str], *, error: str | None = None, contents=None):
    """Build a replacement for search_bm25 / search_vector."""
    contents = contents or {}

    async def _leg(*args, **kwargs):
        if error:
            return LegResult(leg=leg_name, error=error, elapsed_ms=1), {}
        chunks = {cid: make_chunk(cid, contents.get(cid, f"content of {cid}")) for cid in chunk_ids}
        scores = {cid: 1.0 - index * 0.1 for index, cid in enumerate(chunk_ids)}
        return LegResult(leg=leg_name, chunk_ids=chunk_ids, scores=scores, elapsed_ms=1), chunks

    return _leg


@pytest.fixture
def settings() -> Settings:
    # Explicit rather than get_settings() so a stray .env cannot change what
    # these tests assert.
    return Settings(
        retrieval_candidates_per_leg=20,
        retrieval_fusion_top_k=20,
        rerank_top_k=3,
        conditional_rerank_enabled=False,
        reranker_enabled=True,
        groq_api_key="x",  # satisfies nothing here, but keeps Settings realistic
    )


@pytest.fixture
def scope():
    return TenantScope(pool=None, tenant_id="acme")


# ------------------------------------------------------------------ modes --


async def test_hybrid_runs_both_legs_and_fuses(monkeypatch, settings, scope):
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["a", "b"]))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["b", "c"]))

    service = RetrievalService(StubEmbeddings(), settings, reranker=None)
    result = await service.retrieve(scope, "q", mode="hybrid", top_k=10)

    assert {leg.leg for leg in result.legs} == {LEG_BM25, LEG_VECTOR}
    # "b" was found by both legs, so RRF promotes it to first.
    assert [s.chunk.chunk_id for s in result.results][0] == "b"
    assert result.results[0].found_by_both_legs is True


async def test_bm25_mode_skips_the_vector_leg_and_the_embedding(monkeypatch, settings, scope):
    """Embedding is skipped for BM25-only mode on purpose: paying ~15ms of
    CPU for an unused vector would inflate the BM25 arm's latency in Phase
    4's comparison table and make the wrong strategy look slow."""
    called = {"vector": False}

    async def _vector(*args, **kwargs):
        called["vector"] = True
        return LegResult(leg=LEG_VECTOR), {}

    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["a"]))
    monkeypatch.setattr(vector_module, "search_vector", _vector)

    embeddings = StubEmbeddings()
    service = RetrievalService(embeddings, settings, reranker=None)
    result = await service.retrieve(scope, "q", mode="bm25")

    assert called["vector"] is False
    assert embeddings.query_calls == 0
    assert result.embed_ms == 0
    assert [leg.leg for leg in result.legs] == [LEG_BM25]


async def test_vector_mode_skips_the_bm25_leg(monkeypatch, settings, scope):
    called = {"bm25": False}

    async def _bm25(*args, **kwargs):
        called["bm25"] = True
        return LegResult(leg=LEG_BM25), {}

    monkeypatch.setattr(bm25_module, "search_bm25", _bm25)
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["a"]))

    embeddings = StubEmbeddings()
    result = await RetrievalService(embeddings, settings, reranker=None).retrieve(
        scope, "q", mode="vector"
    )

    assert called["bm25"] is False
    assert embeddings.query_calls == 1
    assert [leg.leg for leg in result.legs] == [LEG_VECTOR]


async def test_single_leg_mode_preserves_that_legs_order(monkeypatch, settings, scope):
    """RRF over one list must be a no-op on ordering, or the single-leg arms
    of the Phase 4 table would be comparing a reshuffled BM25 to real BM25."""
    order = [f"c{i}" for i in range(10)]
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, order))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="bm25", top_k=10
    )
    assert [s.chunk.chunk_id for s in result.results] == order


# ------------------------------------------------------------- degradation --


async def test_one_dead_leg_degrades_instead_of_failing(monkeypatch, settings, scope):
    """Answering from one leg is worse than two and far better than a 500."""
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, [], error="boom"))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["a", "b"]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="hybrid"
    )

    assert result.degraded_legs == [LEG_BM25]
    assert [s.chunk.chunk_id for s in result.results] == ["a", "b"]


async def test_a_failed_leg_contributes_no_evidence(monkeypatch, settings, scope):
    """A leg that ERRORED must not appear in a candidate's `ranks` as though
    it simply found nothing — those are different statements, and the
    playground renders both."""
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, [], error="boom"))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["a"]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="hybrid"
    )
    assert result.results[0].bm25_rank is None
    assert result.results[0].found_by_both_legs is False


async def test_all_legs_failing_raises(monkeypatch, settings, scope):
    """Both legs down means the database is unreachable — not 'no results'.
    Phase 3 must abstain on this, and it cannot tell the difference if we
    return an empty result."""
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, [], error="boom"))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, [], error="bang"))

    with pytest.raises(AllLegsFailedError, match="boom"):
        await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
            scope, "q", mode="hybrid"
        )


async def test_no_matches_returns_an_empty_result_not_an_error(monkeypatch, settings, scope):
    """An out-of-scope question legitimately matches nothing. top_score must
    be 0.0 so Phase 3's gate abstains — no evidence must never clear a
    threshold."""
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, []))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, []))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="hybrid"
    )

    assert result.results == []
    assert result.top_score == 0.0
    assert result.chunk_ids() == []


# ---------------------------------------------------------------- evidence --


async def test_per_leg_ranks_and_scores_are_attached(monkeypatch, settings, scope):
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["x", "y"]))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["y"]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="hybrid", top_k=10
    )
    by_id = {s.chunk.chunk_id: s for s in result.results}

    assert by_id["y"].bm25_rank == 2 and by_id["y"].vector_rank == 1
    assert by_id["y"].bm25_score == pytest.approx(0.9)
    assert by_id["x"].vector_rank is None and by_id["x"].vector_score is None


async def test_candidates_are_kept_beyond_top_k(monkeypatch, settings, scope):
    """recall@20 (Phase 4) needs the full fused list, and "the reranker
    demoted the right chunk" is only diagnosable if we keep it."""
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, [f"c{i}" for i in range(15)]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="bm25", top_k=3
    )

    assert len(result.results) == 3
    assert len(result.candidates) == 15


# ---------------------------------------------------------------- rerank --


async def test_reranker_runs_and_reorders(monkeypatch, settings, scope):
    monkeypatch.setattr(
        bm25_module, "search_bm25",
        stub_leg(LEG_BM25, ["wrong", "right"],
                 contents={"wrong": "billing invoices", "right": "webhook retry logic"}),
    )
    reranker = FakeReranker({"webhook": 5.0}, default=-5.0)

    result = await RetrievalService(StubEmbeddings(), settings, reranker=reranker).retrieve(
        scope, "webhooks", mode="bm25", top_k=5
    )

    assert result.rerank.reranked is True
    assert [s.chunk.chunk_id for s in result.results] == ["right", "wrong"]
    assert result.results[0].rerank_score is not None


async def test_no_reranker_means_fusion_order_is_final(monkeypatch, settings, scope):
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["a", "b"]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="bm25"
    )

    assert result.rerank.reranked is False
    assert result.rerank.reason == "reranker_disabled"
    assert [s.chunk.chunk_id for s in result.results] == ["a", "b"]
    assert all(s.rerank_score is None for s in result.results)


async def test_conditional_gate_can_skip_the_reranker(monkeypatch, scope):
    """With the gate ON and an unambiguous fusion, the cross-encoder is
    skipped — the latency saving the gate exists for."""
    gated = Settings(conditional_rerank_enabled=True, rerank_margin_threshold=0.01,
                     rerank_ambiguity_window=5, rerank_top_k=3)
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["a", "b", "c", "d", "e"]))
    reranker = FakeReranker({"content": 9.0})

    result = await RetrievalService(StubEmbeddings(), gated, reranker=reranker).retrieve(
        scope, "q", mode="bm25"
    )

    assert result.rerank.reranked is False
    assert result.rerank.reason == "clear_winner"
    assert reranker.calls == 0
    assert result.rerank_ms == 0


async def test_timings_are_recorded(monkeypatch, settings, scope):
    monkeypatch.setattr(bm25_module, "search_bm25", stub_leg(LEG_BM25, ["a", "b"]))
    monkeypatch.setattr(vector_module, "search_vector", stub_leg(LEG_VECTOR, ["b"]))

    result = await RetrievalService(StubEmbeddings(), settings, reranker=None).retrieve(
        scope, "q", mode="hybrid"
    )

    assert result.retrieval_ms >= 0
    assert result.total_ms >= result.retrieval_ms
    assert all(leg.elapsed_ms >= 0 for leg in result.legs)
