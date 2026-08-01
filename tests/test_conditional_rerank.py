"""The conditional-reranking gate: every branch, and the boundaries.

conditional.py is pure arithmetic plus a decision tree, so this file covers
it exhaustively. The branch ORDER matters as much as the branches — a
decision needs the honest reason attached, not just the right boolean.
"""

import pytest

from app.retrieval.conditional import (
    REASON_AMBIGUOUS,
    REASON_CLEAR_WINNER,
    REASON_DEGENERATE,
    REASON_DISABLED,
    REASON_GATE_OFF,
    REASON_TOO_FEW,
    compute_margin,
    should_rerank,
)

# Phase 2 defaults, mirrored from app/config.py.
WINDOW = 5
THRESHOLD = 0.30


def decide(scores, *, reranker_enabled=True, gate_enabled=True):
    return should_rerank(
        scores,
        reranker_enabled=reranker_enabled,
        gate_enabled=gate_enabled,
        window=WINDOW,
        threshold=THRESHOLD,
    )


# ------------------------------------------------------------- the margin --


def test_margin_is_relative_not_absolute():
    """(s1 - sN) / s1. Relative is the whole point: RRF scores shrink as
    candidate lists lengthen, and an absolute gap would drift with them."""
    assert compute_margin([1.0, 0.9, 0.8, 0.7, 0.5], WINDOW) == pytest.approx(0.5)
    # Same SHAPE, tenth of the magnitude -> same margin.
    assert compute_margin([0.1, 0.09, 0.08, 0.07, 0.05], WINDOW) == pytest.approx(0.5)


def test_margin_window_is_capped_at_list_length():
    """A 3-item list with a window of 5 compares first to last, rather than
    raising or silently reading past the end."""
    assert compute_margin([1.0, 0.9, 0.6], WINDOW) == pytest.approx(0.4)


def test_margin_undefined_cases():
    assert compute_margin([], WINDOW) is None
    assert compute_margin([1.0], WINDOW) is None       # nothing to compare to
    assert compute_margin([0.0, 0.0], WINDOW) is None  # division by zero
    assert compute_margin([-1.0, -2.0], WINDOW) is None


def test_flat_scores_have_zero_margin():
    """Maximum ambiguity: every candidate looks identical."""
    assert compute_margin([0.02] * 5, WINDOW) == pytest.approx(0.0)


# ------------------------------------------------------- decision branches --


def test_reranker_disabled_short_circuits_everything():
    decision = decide([1.0, 0.99], reranker_enabled=False)
    assert decision.reranked is False
    assert decision.reason == REASON_DISABLED


def test_too_few_candidates_is_checked_before_the_gate_flag():
    """One candidate cannot be reordered, so the honest reason is 'too few',
    not 'gate disabled' — even when the gate is off and would otherwise say
    'always rerank'. Reason codes end up in /stats; a misattributed skip
    would make the dashboard lie about why latency dropped."""
    for gate in (True, False):
        decision = decide([1.0], gate_enabled=gate)
        assert decision.reranked is False
        assert decision.reason == REASON_TOO_FEW
    assert decide([], gate_enabled=False).reason == REASON_TOO_FEW


def test_gate_off_means_always_rerank():
    """The Phase 2 default (ADR-014): the always-rerank arm is the quality
    ceiling Phase 4 measures the conditional arm against."""
    decision = decide([1.0, 0.1, 0.05], gate_enabled=False)
    assert decision.reranked is True
    assert decision.reason == REASON_GATE_OFF
    assert decision.margin is None  # not computed; do not imply we measured


def test_clear_winner_skips_reranking():
    # margin = (1.0 - 0.5) / 1.0 = 0.5 >= 0.30
    decision = decide([1.0, 0.9, 0.8, 0.7, 0.5])
    assert decision.reranked is False
    assert decision.reason == REASON_CLEAR_WINNER
    assert decision.margin == pytest.approx(0.5)
    assert decision.threshold == THRESHOLD


def test_ambiguous_triggers_reranking():
    # margin = (1.0 - 0.9) / 1.0 = 0.1 < 0.30
    decision = decide([1.0, 0.98, 0.95, 0.93, 0.9])
    assert decision.reranked is True
    assert decision.reason == REASON_AMBIGUOUS
    assert decision.margin == pytest.approx(0.1)


def test_threshold_boundary_is_inclusive_on_skip():
    """margin == threshold counts as clear. Documented explicitly because a
    boundary that flips with a floating-point rounding change would make
    Phase 4's tuning sweep noisy right where it matters most."""
    exactly = decide([1.0, 0.9, 0.85, 0.8, 0.7])  # margin = 0.30
    assert exactly.margin == pytest.approx(THRESHOLD)
    assert exactly.reranked is False
    assert exactly.reason == REASON_CLEAR_WINNER

    just_under = decide([1.0, 0.9, 0.85, 0.8, 0.701])
    assert just_under.reranked is True


def test_degenerate_scores_fail_toward_quality():
    """When the cheap ambiguity signal is uninformative we rerank rather than
    guess: in a support system a slow answer costs less than a wrong one."""
    decision = decide([0.0, 0.0, 0.0])
    assert decision.reranked is True
    assert decision.reason == REASON_DEGENERATE
    assert decision.margin is None


def test_candidates_considered_is_always_recorded():
    for scores in ([], [1.0], [1.0, 0.5], [1.0] * 20):
        assert decide(scores).candidates_considered == len(scores)
