"""Retrieval metrics, against hand-computed values.

These get more coverage than almost anything else in the project, for a reason
worth stating: a metric with an off-by-one is not a bug you notice, it is a
number you believe. Every other test protects behaviour; these protect the
instrument you use to judge behaviour, and a broken instrument makes every
other measurement worthless without ever failing.
"""

import pytest

from fishnet.metrics import (
    aggregate,
    case_metrics,
    hit_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    relative_delta,
    summarize,
)


# ------------------------------------------------------------------ recall --


def test_recall_counts_expected_chunks_found_in_the_window():
    retrieved = ["a", "b", "c", "d", "e", "f"]
    assert recall_at_k(retrieved, {"a", "c"}, 5) == pytest.approx(1.0)
    assert recall_at_k(retrieved, {"a", "f"}, 5) == pytest.approx(0.5)   # f is at rank 6
    assert recall_at_k(retrieved, {"a", "f"}, 20) == pytest.approx(1.0)
    assert recall_at_k(retrieved, {"x", "y"}, 5) == pytest.approx(0.0)


def test_recall_is_one_when_nothing_was_expected():
    """The out-of-scope convention. There was nothing to find, so nothing was
    missed — returning 0.0 would make every must-abstain case drag the
    aggregate down and punish exactly the behaviour we want."""
    assert recall_at_k([], set(), 5) == 1.0
    assert recall_at_k(["a", "b"], set(), 5) == 1.0


def test_recall_at_5_and_20_differ_when_the_hit_is_deep():
    """The distinction that makes both worth reporting: recall@20 measures
    first-stage retrieval, recall@5 measures what survives reranking."""
    retrieved = [f"c{i}" for i in range(20)]
    assert recall_at_k(retrieved, {"c12"}, 5) == 0.0
    assert recall_at_k(retrieved, {"c12"}, 20) == 1.0


# --------------------------------------------------------------- precision --


def test_precision_divides_by_the_window_actually_returned():
    """Not by k. Dividing by k would penalize a system for returning 3
    excellent results when only 3 exist — punishing it for the corpus being
    small rather than for being wrong."""
    assert precision_at_k(["a", "b", "c"], {"a", "b", "c"}, 5) == pytest.approx(1.0)
    assert precision_at_k(["a", "b", "c"], {"a"}, 5) == pytest.approx(1 / 3)


def test_precision_on_empty_retrieval():
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_precision_and_recall_pull_against_each_other():
    """Why both are reported. Retrieving everything maximizes recall and
    destroys precision — a single 'quality' number would hide the trade."""
    retrieved = [f"c{i}" for i in range(20)]
    expected = {"c0"}
    assert recall_at_k(retrieved, expected, 20) == 1.0
    assert precision_at_k(retrieved, expected, 20) == pytest.approx(0.05)


# --------------------------------------------------------------------- MRR --


def test_reciprocal_rank_is_one_over_the_first_hit_position():
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == pytest.approx(1.0)
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == pytest.approx(0.5)
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b", "c"], {"z"}) == 0.0


def test_mrr_sees_what_recall_cannot():
    """Two systems, identical recall@5, different rank of the right answer.
    With position-sensitive generation downstream, that difference is real."""
    expected = {"answer"}
    good = ["answer", "x", "y", "z", "w"]
    poor = ["x", "y", "z", "w", "answer"]

    assert recall_at_k(good, expected, 5) == recall_at_k(poor, expected, 5) == 1.0
    assert reciprocal_rank(good, expected) == 1.0
    assert reciprocal_rank(poor, expected) == pytest.approx(0.2)


def test_mrr_uses_only_the_first_hit():
    """By definition. A second correct chunk at rank 5 does not improve MRR —
    that is recall's job, and conflating them would double-count."""
    assert reciprocal_rank(["a", "x", "b"], {"a", "b"}) == pytest.approx(1.0)


# --------------------------------------------------------------------- hit --


def test_hit_at_k_is_binary():
    assert hit_at_k(["a", "b"], {"a", "z"}, 5) is True
    assert hit_at_k(["a", "b"], {"z"}, 5) is False
    assert hit_at_k([], set(), 5) is True


# ------------------------------------------------------------- aggregation --


def test_aggregate_handles_empty():
    assert aggregate([]) == 0.0
    assert aggregate([1.0, 0.0]) == pytest.approx(0.5)


def test_summarize_reports_overall_and_per_case_type():
    """The per-type split is the whole value. 'recall@5 = 0.82' is a number;
    '0.95 on normal, 0.41 on exact-identifier' names the component to fix."""
    per_case = [
        ("normal", {"recall@5": 1.0}),
        ("normal", {"recall@5": 1.0}),
        ("exact_identifier", {"recall@5": 0.0}),
        ("exact_identifier", {"recall@5": 1.0}),
    ]
    summary = summarize(per_case)

    assert summary["overall"]["recall@5"] == pytest.approx(0.75)
    assert summary["normal"]["recall@5"] == pytest.approx(1.0)
    assert summary["exact_identifier"]["recall@5"] == pytest.approx(0.5)


def test_summarize_macro_averages_over_cases():
    """Every case weighs the same, so one case expecting six chunks cannot
    dominate fifty cases expecting one. Micro-averaging would let corpus shape
    drive the headline number."""
    per_case = [("normal", {"m": 1.0})] * 9 + [("normal", {"m": 0.0})]
    assert summarize(per_case)["overall"]["m"] == pytest.approx(0.9)


def test_case_metrics_bundle_is_complete():
    metrics = case_metrics(["a", "b"], {"a"})
    assert set(metrics) == {"recall@5", "recall@20", "precision@5", "mrr", "hit@5"}


# ---------------------------------------------------- relative delta (CI) --


def test_relative_delta_basics():
    assert relative_delta(0.9, 1.0) == pytest.approx(-0.1)
    assert relative_delta(1.1, 1.0) == pytest.approx(0.1)
    assert relative_delta(1.0, 1.0) == 0.0


def test_relative_delta_guards_division_by_zero():
    """A baseline of 0.0 must not produce inf or NaN. NaN compares False
    against every threshold, so a regression gate would silently pass —
    the worst possible failure for a gate."""
    assert relative_delta(0.0, 0.0) == 0.0
    assert relative_delta(0.5, 0.0) == 1.0


def test_relative_delta_of_a_negative_baseline_uses_magnitude():
    assert relative_delta(-1.5, -1.0) == pytest.approx(-0.5)
