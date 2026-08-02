"""Retrieval metrics (Design.md §12).

Pure functions over ordered id lists — no database, no config, no async. That
is what makes them exhaustively testable against hand-computed values, which
matters more here than anywhere else in the codebase: a metric with an
off-by-one is not a bug you notice, it is a number you believe.

The four, and what each one actually tells you:

  recall@k     Of the chunks that SHOULD have been found, what fraction landed
               in the top k? The headline number for a RAG system, because a
               chunk that never reaches the LLM cannot be cited. recall@20
               measures first-stage retrieval; recall@5 measures what actually
               reaches the model after reranking.

  precision@k  Of the top k, what fraction were relevant? Pulls against
               recall. Matters because irrelevant context is not free — it
               costs tokens and dilutes attention (Design.md §4's
               "needle in a haystack").

  MRR          1 / (rank of the first correct chunk), averaged. Rewards
               getting a right answer to the TOP, not merely into the list.
               Two systems can have identical recall@5 while one puts the
               answer first and the other fifth; only MRR sees the difference,
               and with a reranker feeding position-sensitive generation, that
               difference is real.

Why report all four, per case type. An aggregate hides the interesting
failures: a system can score 0.85 recall overall while getting every
exact-identifier case wrong — and identifier queries are the entire reason the
BM25 leg exists (Design.md §5). One number cannot tell you that.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean


def recall_at_k(retrieved: list[str], expected: set[str], k: int) -> float:
    """Fraction of expected chunks appearing in the top k.

    Returns 1.0 when nothing was expected. That is the correct convention for
    out-of-scope cases: there was nothing to find, so nothing was missed.
    Returning 0.0 would make every must-abstain case drag the aggregate down
    and punish the behavior we want.
    """
    if not expected:
        return 1.0
    hits = len(expected & set(retrieved[:k]))
    return hits / len(expected)


def precision_at_k(retrieved: list[str], expected: set[str], k: int) -> float:
    """Fraction of the top k that were expected.

    Denominator is `min(k, len(retrieved))`, not k. Dividing by k would
    penalize a system for returning 3 excellent results when only 3 exist —
    punishing it for the corpus being small rather than for being wrong.
    """
    if not expected:
        return 1.0
    window = retrieved[:k]
    if not window:
        return 0.0
    return len(expected & set(window)) / len(window)


def reciprocal_rank(retrieved: list[str], expected: set[str]) -> float:
    """1 / (1-based rank of the first correct chunk), or 0.0 if none appear."""
    if not expected:
        return 1.0
    for position, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in expected:
            return 1.0 / position
    return 0.0


def hit_at_k(retrieved: list[str], expected: set[str], k: int) -> bool:
    """Did ANY correct chunk make the top k?

    Coarser than recall and sometimes the more honest question: for a query
    with one right answer, recall@5 is either 0 or 1 anyway, and phrasing it
    as a hit rate stops people reading a binary as a continuous quality score.
    """
    if not expected:
        return True
    return bool(expected & set(retrieved[:k]))


# ------------------------------------------------------------ aggregation --


def aggregate(values: list[float]) -> float:
    """Mean, or 0.0 for an empty list.

    Macro-averaging (mean over CASES, not over retrieved chunks) is
    deliberate: it gives every case equal weight, so a single case expecting
    six chunks cannot dominate the score of fifty cases expecting one.
    Micro-averaging would let corpus shape drive the headline number.
    """
    return mean(values) if values else 0.0


def summarize(
    per_case: list[tuple[str, dict[str, float]]]
) -> dict[str, dict[str, float]]:
    """Aggregate per-case metrics overall and by case type.

    Args:
        per_case: (case_type, {metric_name: value}) for each case.

    Returns:
        {"overall": {...}, "<case_type>": {...}, ...}

    The per-type breakdown is the point. "recall@5 = 0.82" is a number;
    "recall@5 = 0.95 on normal cases, 0.41 on exact-identifier cases" is a
    finding, and it names the component to fix.
    """
    by_group: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for case_type, metrics in per_case:
        for name, value in metrics.items():
            by_group["overall"][name].append(value)
            by_group[case_type][name].append(value)

    return {
        group: {name: aggregate(values) for name, values in metrics.items()}
        for group, metrics in by_group.items()
    }


def case_metrics(retrieved: list[str], expected: set[str]) -> dict[str, float]:
    """The standard metric bundle for one case."""
    return {
        "recall@5": recall_at_k(retrieved, expected, 5),
        "recall@20": recall_at_k(retrieved, expected, 20),
        "precision@5": precision_at_k(retrieved, expected, 5),
        "mrr": reciprocal_rank(retrieved, expected),
        "hit@5": float(hit_at_k(retrieved, expected, 5)),
    }


def relative_delta(new: float, old: float) -> float:
    """Relative change, used by the baseline regression check.

    Guards the degenerate cases explicitly rather than letting them produce
    inf or NaN, which would either crash CI or — worse — compare as False
    against every threshold and silently pass.
    """
    if old == 0:
        return 0.0 if new == 0 else 1.0
    return (new - old) / abs(old)
