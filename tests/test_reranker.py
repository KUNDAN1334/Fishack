"""Reranker behavior, with a fake cross-encoder.

No torch, no 280MB download, no CPU forward pass — the Reranker Protocol
exists precisely so this suite stays instant. What we assert here is
everything ABOUT the reranker that is our code rather than the model's:
score normalization, ordering, top_k, in-place annotation, and the
misalignment guard.
"""

import datetime as dt

import pytest

from app.retrieval.models import RetrievedChunk, ScoredChunk
from app.retrieval.reranker import rerank_candidates, sigmoid


class FakeCrossEncoder:
    """Returns scripted logits, in the order passages were given.

    `scores_by_content` maps a substring to the logit it should produce, so
    tests read as "the chunk about webhooks scores high" rather than as index
    arithmetic.
    """

    def __init__(self, scores_by_content: dict[str, float], default: float = -5.0):
        self.scores_by_content = scores_by_content
        self.default = default
        self.calls: list[tuple[str, int]] = []  # (query, n_passages)

    def score_pairs(self, query, passages):
        self.calls.append((query, len(passages)))
        scores = []
        for passage in passages:
            match = next(
                (score for key, score in self.scores_by_content.items() if key in passage),
                self.default,
            )
            scores.append(match)
        return scores


class BrokenCrossEncoder:
    """Returns the wrong number of scores — the misalignment bug."""

    def score_pairs(self, query, passages):
        return [1.0] * (len(passages) - 1)


def make_candidate(chunk_id: str, content: str, fused_score: float = 0.01) -> ScoredChunk:
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=chunk_id,
            document_id=f"doc-{chunk_id}",
            tenant_id="acme",
            content=content,
            effective_date=dt.date(2026, 1, 1),
        ),
        fused_score=fused_score,
    )


# ------------------------------------------------------------- the sigmoid --


def test_sigmoid_maps_logits_into_zero_one():
    assert sigmoid(0.0) == pytest.approx(0.5)
    assert sigmoid(10.0) > 0.999
    assert sigmoid(-10.0) < 0.001
    # Real bge-reranker logits live in roughly -11..+11, so extremes are
    # defensive rather than expected.
    assert 0.0 <= sigmoid(-800.0) <= 1.0
    assert 0.0 <= sigmoid(800.0) <= 1.0


def test_sigmoid_branch_prevents_an_overflow_the_naive_formula_would_hit():
    """Why the two-branch implementation exists, demonstrated.

    `1 / (1 + exp(-x))` raises OverflowError for a large NEGATIVE x, because
    `exp(-x)` becomes inf. Our branch computes `exp(x)/(1+exp(x))` there
    instead, which underflows harmlessly toward 0.0. Underflow gives a wrong-
    but-bounded answer; overflow gives a traceback in the middle of a user's
    request.
    """
    import math

    with pytest.raises(OverflowError):
        1.0 / (1.0 + math.exp(800.0))  # the naive formula at x = -800

    assert sigmoid(-800.0) == 0.0  # ours: saturates instead of raising


def test_sigmoid_is_monotonic():
    """Monotonicity is why we can sort on the raw logit and report the
    squashed score without the two disagreeing."""
    values = [sigmoid(x) for x in range(-20, 21)]
    assert values == sorted(values)


# ---------------------------------------------------------------- ordering --


def test_reranker_can_overturn_the_fusion_order():
    """The reason the reranker exists: first-stage retrieval put the wrong
    chunk first, and a cross-encoder that reads query and passage together
    fixes it."""
    candidates = [
        make_candidate("wrong", "Billing invoices and proration", fused_score=0.03),
        make_candidate("right", "Webhook retry logic and backoff", fused_score=0.02),
    ]
    reranker = FakeCrossEncoder({"Webhook": 8.0, "Billing": -3.0})

    results, elapsed_ms = rerank_candidates(
        reranker, "why do my webhooks retry", candidates, top_k=5
    )

    assert [item.chunk.chunk_id for item in results] == ["right", "wrong"]
    assert results[0].rerank_rank == 1
    assert results[1].rerank_rank == 2
    assert elapsed_ms >= 0


def test_both_scores_are_recorded():
    """rerank_score is the 0-1 number thresholds use; rerank_score_raw is the
    model's actual output. Losing the raw value makes "why did the gate not
    fire" unanswerable."""
    candidates = [make_candidate("a", "Webhook retry logic")]
    results, _ = rerank_candidates(FakeCrossEncoder({"Webhook": 2.0}), "q", candidates, top_k=5)

    assert results[0].rerank_score_raw == pytest.approx(2.0)
    assert results[0].rerank_score == pytest.approx(sigmoid(2.0))
    assert 0.0 < results[0].rerank_score < 1.0


def test_final_score_prefers_the_reranker_but_falls_back_to_fusion():
    unreranked = make_candidate("a", "text", fused_score=0.025)
    assert unreranked.final_score == pytest.approx(0.025)

    rerank_candidates(FakeCrossEncoder({"text": 1.0}), "q", [unreranked], top_k=1)
    assert unreranked.final_score == pytest.approx(sigmoid(1.0))


def test_top_k_truncates_results_but_annotates_every_candidate():
    """Truncation applies to what we RETURN; every candidate still gets its
    score, because Phase 4 needs to see that the reranker demoted the correct
    chunk from rank 2 to rank 14."""
    candidates = [make_candidate(f"c{i}", f"content {i}") for i in range(10)]
    reranker = FakeCrossEncoder({"content 7": 9.0})

    results, _ = rerank_candidates(reranker, "q", candidates, top_k=3)

    assert len(results) == 3
    assert results[0].chunk.chunk_id == "c7"
    assert all(candidate.rerank_score is not None for candidate in candidates)
    assert all(candidate.rerank_rank is not None for candidate in candidates)


def test_ties_broken_by_chunk_id_for_reproducibility():
    candidates = [make_candidate("zeta", "same"), make_candidate("alpha", "same")]
    results, _ = rerank_candidates(FakeCrossEncoder({"same": 1.0}), "q", candidates, top_k=5)
    assert [item.chunk.chunk_id for item in results] == ["alpha", "zeta"]


# ------------------------------------------------------------ error paths --


def test_empty_candidates_is_a_no_op():
    results, elapsed_ms = rerank_candidates(FakeCrossEncoder({}), "q", [], top_k=5)
    assert results == []
    assert elapsed_ms == 0


def test_score_count_mismatch_raises_instead_of_misaligning():
    """A reranker returning the wrong number of scores would zip chunks to
    the wrong scores — every answer would cite the wrong sources while
    looking perfectly healthy. Loud failure only."""
    candidates = [make_candidate(f"c{i}", f"text {i}") for i in range(3)]
    with pytest.raises(ValueError, match="returned 2 scores for 3 candidates"):
        rerank_candidates(BrokenCrossEncoder(), "q", candidates, top_k=5)


def test_oversized_candidates_are_warned_about(caplog):
    """Silent truncation at the cross-encoder's window would score a passage
    the model only half-read."""
    big = make_candidate("big", "x" * 5000)
    with caplog.at_level("WARNING"):
        rerank_candidates(FakeCrossEncoder({}), "q", [big], top_k=1, max_length=512)
    assert any("truncated" in record.message for record in caplog.records)
