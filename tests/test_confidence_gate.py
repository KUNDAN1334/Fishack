"""The confidence gate — Design.md §7 technique 5.

Pure function over a RetrievalResult, so every branch is covered here without
a database or a model. The two-scale behavior is the part worth the most
attention: a single threshold across reranker and RRF scores would be wrong by
roughly 30x for one of them, and wrong silently.
"""

import datetime as dt

import pytest

from app.generation.gate import (
    REASON_BELOW_THRESHOLD,
    REASON_CONFIDENT,
    REASON_NO_RESULTS,
    evaluate_gate,
)
from app.retrieval.models import RetrievalResult, RetrievedChunk, ScoredChunk

THRESHOLD_RERANK = 0.45
THRESHOLD_FUSED = 0.015


def scored(*, rerank: float | None = None, fused: float = 0.02) -> ScoredChunk:
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id="c1", document_id="d1", tenant_id="acme",
            content="body", effective_date=dt.date(2026, 1, 1),
        ),
        fused_score=fused,
        rerank_score=rerank,
    )


def result(results, **kwargs) -> RetrievalResult:
    return RetrievalResult(
        query="q", tenant_id="acme", mode="hybrid", results=results, **kwargs
    )


def gate(retrieval):
    return evaluate_gate(
        retrieval,
        threshold_rerank=THRESHOLD_RERANK,
        threshold_fused=THRESHOLD_FUSED,
    )


# ------------------------------------------------------------ no results --


def test_no_results_never_generates():
    """The out-of-scope case, and the golden set's must-abstain cases.

    top_score is 0.0 so no threshold value can ever admit it — that is a
    property worth having, because a tuning sweep must not be able to
    accidentally configure the system into answering questions it retrieved
    nothing for.
    """
    decision = gate(result([]))
    assert decision.should_generate is False
    assert decision.reason == REASON_NO_RESULTS
    assert decision.top_score == 0.0
    assert decision.score_kind == "none"


def test_no_results_stays_abstained_at_a_zero_threshold():
    decision = evaluate_gate(result([]), threshold_rerank=0.0, threshold_fused=0.0)
    assert decision.should_generate is False


# ------------------------------------------------- which scale is in use --


def test_uses_the_rerank_threshold_when_the_reranker_ran():
    """0.5 clears the reranker threshold (0.45) but would be enormous on the
    RRF scale. Reading the wrong scale here would pass everything."""
    decision = gate(result([scored(rerank=0.5, fused=0.001)]))
    assert decision.should_generate is True
    assert decision.score_kind == "rerank"
    assert decision.threshold == THRESHOLD_RERANK


def test_uses_the_fused_threshold_when_the_reranker_did_not_run():
    """0.02 is a healthy RRF score and would be catastrophically low on the
    reranker's 0-1 scale. Reading the wrong scale here would abstain on
    everything."""
    decision = gate(result([scored(rerank=None, fused=0.02)]))
    assert decision.should_generate is True
    assert decision.score_kind == "fused"
    assert decision.threshold == THRESHOLD_FUSED


def test_scale_is_read_from_the_data_not_from_config():
    """Whether reranking actually ran depends on the conditional gate, the
    reranker being loaded, and the candidate count — config alone cannot say.
    A rerank_score of exactly 0.0 is still a rerank score."""
    decision = gate(result([scored(rerank=0.0, fused=0.9)]))
    assert decision.score_kind == "rerank"
    assert decision.should_generate is False


# ------------------------------------------------------------ thresholds --


@pytest.mark.parametrize(
    "rerank_score,expected",
    [(0.9, True), (0.46, True), (0.45, True), (0.4499, False), (0.1, False)],
)
def test_rerank_threshold_boundary_is_inclusive(rerank_score, expected):
    """`score >= threshold` passes. Pinned because Phase 4's tuning script
    sweeps this boundary, and a flip in inclusivity would shift every tuned
    value by one step."""
    assert gate(result([scored(rerank=rerank_score)])).should_generate is expected


@pytest.mark.parametrize(
    "fused_score,expected",
    [(0.033, True), (0.016, True), (0.015, True), (0.0149, False), (0.001, False)],
)
def test_fused_threshold_boundary(fused_score, expected):
    assert gate(result([scored(rerank=None, fused=fused_score)])).should_generate is expected


def test_below_threshold_records_the_numbers_that_produced_the_decision():
    """A trace six weeks old must show WHY, not just what. Without the score,
    the threshold, and the scale, 'abstained' is unactionable."""
    decision = gate(result([scored(rerank=0.2)]))
    assert decision.reason == REASON_BELOW_THRESHOLD
    assert decision.top_score == pytest.approx(0.2)
    assert decision.threshold == THRESHOLD_RERANK
    assert decision.score_kind == "rerank"


def test_only_the_top_result_decides():
    """The gate asks "is our BEST evidence good enough", not "is the average
    good enough". A pile of weak chunks must not average its way past."""
    decision = gate(result([scored(rerank=0.9), scored(rerank=0.01), scored(rerank=0.01)]))
    assert decision.should_generate is True
    assert decision.top_score == pytest.approx(0.9)


# ------------------------------------------------------------- degraded --


def test_a_degraded_leg_does_not_block_a_confident_answer():
    """One dead leg means less evidence, not bad evidence. If what survived
    still scores well, answering from it beats abstaining."""
    decision = gate(result([scored(rerank=0.8)], degraded_legs=["bm25"]))
    assert decision.should_generate is True
    assert decision.reason == REASON_CONFIDENT
