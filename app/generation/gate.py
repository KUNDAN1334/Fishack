"""The confidence gate — abstain BEFORE calling the LLM (Design.md §7.5).

Design.md lists five anti-hallucination techniques. This is the fifth, and the
only one that works by *not running the model*:

    "Retrieval confidence threshold BEFORE generation — don't even call the
     LLM if retrieval score too low, directly abstain (saves cost too!)"

Why before and not after. A model handed five irrelevant chunks and asked to
answer will usually produce something — fluent, plausible, and cited to those
irrelevant chunks. Post-hoc checks then have to detect a well-formed lie. It
is far more reliable to notice that retrieval failed, which is a measurement,
than to notice that generation lied, which is a judgement. Gating on retrieval
also means the failure costs zero tokens and zero latency, and Design.md §9
makes cost a first-class constraint.

The gate's cost, stated honestly: it is the single control most likely to
produce a WRONG abstention. Set it too high and Fishly refuses questions it
could have answered, which users experience as a broken product and which
shows up as a rising escalation rate (Design.md §12 lists that metric for
exactly this reason). Too low and it stops defending anything. That is why
Phase 4 ships a tuning script rather than a number I asserted.

Two thresholds, not one. `ScoredChunk.final_score` is the reranker's sigmoid
(0-1) when reranking ran, and the RRF score (~0.016-0.033) when it did not —
scales that differ by roughly 30x. A single threshold would be calibrated for
at most one of them, and silently wrong for the other. The gate therefore
picks the threshold to match the score it is reading, and records WHICH in the
decision, because "top_score=0.02" is uninterpretable without it.
"""

from __future__ import annotations

import logging

from app.generation.models import GateDecision
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)

REASON_CONFIDENT = "confident"
REASON_NO_RESULTS = "no_results"
REASON_BELOW_THRESHOLD = "below_threshold"
REASON_ALL_LEGS_DEGRADED = "retrieval_degraded"


def evaluate_gate(
    retrieval: RetrievalResult,
    *,
    threshold_rerank: float,
    threshold_fused: float,
) -> GateDecision:
    """Decide whether the retrieved context is strong enough to generate from.

    Pure function over a RetrievalResult — no I/O, no config object — so every
    branch is testable in microseconds and the Phase 4 tuning script can sweep
    thresholds over recorded retrieval results without re-running retrieval.
    That last property is what makes tuning practical at all: re-retrieving 60
    golden cases per threshold value would take minutes per sweep point.
    """
    if not retrieval.results:
        # No candidates at all. Distinct from "candidates scored low": this is
        # an out-of-scope question, and the golden set's must-abstain cases
        # live here. top_score is 0.0, so no threshold can ever admit it.
        return GateDecision(
            should_generate=False,
            reason=REASON_NO_RESULTS,
            top_score=0.0,
            threshold=threshold_fused,
            score_kind="none",
        )

    top = retrieval.results[0]
    # Read the score kind off the data, not off config. Whether reranking
    # actually ran depends on the conditional gate, the reranker being
    # loaded, and the candidate count — config alone cannot tell you.
    if top.rerank_score is not None:
        score, threshold, kind = top.rerank_score, threshold_rerank, "rerank"
    else:
        score, threshold, kind = top.fused_score, threshold_fused, "fused"

    if score < threshold:
        logger.info(
            "confidence gate: abstaining (%s score %.4f < %.4f) for query %r",
            kind, score, threshold, retrieval.query,
        )
        return GateDecision(
            should_generate=False,
            reason=REASON_BELOW_THRESHOLD,
            top_score=score,
            threshold=threshold,
            score_kind=kind,
        )

    if retrieval.degraded_legs:
        # We pass, but note it. A degraded leg means this answer was built on
        # less evidence than usual — worth having on the trace when someone
        # later asks why a particular answer was poor.
        logger.info(
            "confidence gate: passing with degraded legs %s", retrieval.degraded_legs
        )

    return GateDecision(
        should_generate=True,
        reason=REASON_CONFIDENT,
        top_score=score,
        threshold=threshold,
        score_kind=kind,
    )
