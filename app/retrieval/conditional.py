"""Conditional reranking: should we spend the cross-encoder's latency?

Design.md §6 and §13(c) both land on the same idea: a reranker costs
200-500ms (more on CPU), and you do not always need it. If the fusion already
produced an obvious winner, reordering it is expensive agreement. Run the
reranker only when the top of the list is AMBIGUOUS.

The rule implemented here:

    margin = (s1 - sN) / s1        over FUSED scores, N = ambiguity window
    margin >= threshold  ->  clear winner, skip the reranker
    margin <  threshold  ->  ambiguous, rerank

Why the margin is computed on RRF scores and not on raw leg scores: RRF
scores depend only on ranks and k, so they occupy the same numeric range for
every query. That is precisely what makes a RELATIVE threshold portable. Raw
BM25 scores are corpus- and query-dependent — a 0.30 margin would mean
something different for every query, and the threshold would be untunable.

Why this is a proxy, stated plainly: the margin measures how much the two
legs AGREE, not whether they are RIGHT. If BM25 and vector both confidently
rank the same wrong chunk first, the margin looks clean and we skip the
reranker that would have fixed it. That failure mode is invisible to this
function by construction. Phase 4 measures how often it happens by running
the golden set with the gate on and off (ADR-014); until then the gate ships
DISABLED so the always-rerank arm remains the quality ceiling.

Pure module: no config object, no I/O, no model. Just numbers in, decision
out — so every branch is unit-testable in microseconds.
"""

from __future__ import annotations

from app.retrieval.models import RerankDecision

# Reason codes. Constants rather than inline strings because these end up in
# traces and in /stats aggregations (Phase 5) — a typo'd reason would quietly
# create a second bucket in a dashboard.
REASON_DISABLED = "reranker_disabled"
REASON_GATE_OFF = "gate_disabled"
REASON_TOO_FEW = "too_few_candidates"
REASON_CLEAR_WINNER = "clear_winner"
REASON_AMBIGUOUS = "ambiguous"
REASON_DEGENERATE = "degenerate_scores"


def compute_margin(scores: list[float], window: int) -> float | None:
    """Relative gap between the best score and the window-th best.

    Returns None when the margin is undefined — fewer than two scores, or a
    non-positive top score (which would make the division meaningless rather
    than merely uninformative).

    The window is capped at the number of available scores, so a short
    candidate list compares first-to-last instead of erroring.
    """
    if len(scores) < 2:
        return None

    top = scores[0]
    if top <= 0:
        return None

    # `window` is 1-based ("how deep do we look"), so index window-1.
    index = min(window, len(scores)) - 1
    return (top - scores[index]) / top


def should_rerank(
    fused_scores: list[float],
    *,
    reranker_enabled: bool,
    gate_enabled: bool,
    window: int,
    threshold: float,
) -> RerankDecision:
    """Decide whether the cross-encoder runs, and record why.

    Args:
        fused_scores: RRF scores, already sorted best-first.
        reranker_enabled: config kill switch for the reranker entirely.
        gate_enabled: config flag for CONDITIONAL reranking. False means
            "always rerank" — the Phase 2 default (ADR-014).
        window: how far down the list to measure the margin.
        threshold: margin at or above which the top result counts as clear.

    Returns a RerankDecision rather than a bool: a trace six weeks old needs
    the reason and the numbers, not just the outcome.
    """
    count = len(fused_scores)

    # Order of checks matters — each answers a different question, and the
    # first one that applies is the honest explanation for the decision.

    # 1. Is the reranker available at all?
    if not reranker_enabled:
        return RerankDecision(
            reranked=False, reason=REASON_DISABLED, candidates_considered=count
        )

    # 2. Is there anything to reorder? One (or zero) candidate cannot be
    #    reranked into a different order, so the latency would buy nothing.
    #    Checked before the gate flag because it is true regardless of config.
    if count < 2:
        return RerankDecision(
            reranked=False, reason=REASON_TOO_FEW, candidates_considered=count
        )

    # 3. Gate off -> always rerank (the Phase 2 default: quality ceiling).
    if not gate_enabled:
        return RerankDecision(
            reranked=True, reason=REASON_GATE_OFF, candidates_considered=count
        )

    # 4. Gate on -> measure ambiguity.
    margin = compute_margin(fused_scores, window)
    if margin is None:
        # Degenerate scores (all zero, or a non-positive top). We cannot tell
        # whether the list is ambiguous, so we rerank — when the cheap signal
        # is uninformative, fall back to the expensive-but-accurate path
        # rather than guessing. Failing toward quality is the right default
        # for a support system (Design.md: a wrong answer costs more than a
        # slow one).
        return RerankDecision(
            reranked=True,
            reason=REASON_DEGENERATE,
            threshold=threshold,
            candidates_considered=count,
        )

    if margin >= threshold:
        return RerankDecision(
            reranked=False,
            reason=REASON_CLEAR_WINNER,
            margin=margin,
            threshold=threshold,
            candidates_considered=count,
        )

    return RerankDecision(
        reranked=True,
        reason=REASON_AMBIGUOUS,
        margin=margin,
        threshold=threshold,
        candidates_considered=count,
    )
