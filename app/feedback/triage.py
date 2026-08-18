"""Classifying a thumbs-down (Design.md §10).

    "👎 triage:
       Retrieval problem  (right chunks nahi mile)  -> retrieval quality issue
       Generation problem (right chunks the, answer galat bana) -> prompt issue
       Stale data                                    -> ingestion issue"

Why this matters more than it sounds: those three failures have completely
different fixes. Retrieval failures are fixed by chunking, embeddings or
fusion weights. Generation failures are fixed by the prompt. Stale-data
failures are fixed by ingestion. A pile of undifferentiated 👎 tells you the
system is bad; a classified pile tells you which component to open.

WHY HEURISTICS RATHER THAN AN LLM. Every signal needed is already on the trace
row — confidence, the score scale, the citation report, whether a contested
chunk was cited. The classification is therefore free, instant, deterministic,
and explainable ("classified as retrieval failure because confidence was 0.31
against a 0.45 threshold"). An LLM classifier would cost quota, vary between
runs, and could not be checked. `# PRODUCTION NOTE:` at volume you would use
an LLM for the residual `unclear` bucket only — which is why that bucket
exists and is reported separately rather than being forced into a category.

Pure functions over a dict, so a trace row from Postgres and a hand-written
fixture in a test go through exactly the same code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Categories. Constants because they end up in reports and aggregations, where
# a typo would silently create a second bucket.
RETRIEVAL_FAILURE = "retrieval"
GENERATION_FAILURE = "generation"
STALE_DATA = "stale_data"
CACHE_FAILURE = "cache"
UNCLEAR = "unclear"

FIXES = {
    RETRIEVAL_FAILURE: "chunking / embeddings / fusion weights — the right chunks never arrived",
    GENERATION_FAILURE: "the prompt — the right chunks arrived and the answer was still wrong",
    STALE_DATA: "ingestion — a superseded or contested source was cited as current",
    CACHE_FAILURE: "cache thresholds — a stored answer was served for a different question",
    UNCLEAR: "needs a human — the trace does not distinguish the failure modes",
}


@dataclass
class Triage:
    """One classified thumbs-down."""

    trace_id: str
    category: str
    reason: str
    query: str = ""
    confidence: float = 0.0
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def suggested_fix(self) -> str:
        return FIXES.get(self.category, FIXES[UNCLEAR])


def classify(trace: dict) -> Triage:
    """Decide why this answer was bad, from the trace alone.

    Order matters. Each check answers a different question, and the FIRST one
    that applies is the honest explanation — checking generation before
    retrieval, for example, would blame the prompt for chunks that never
    arrived.
    """
    trace_id = str(trace.get("id", ""))
    query = trace.get("query") or ""
    confidence = float(trace.get("confidence") or 0.0)
    action = trace.get("action")
    cache_status = trace.get("cache_status") or "miss"
    report = trace.get("citation_report") or {}
    chunk_ids = trace.get("retrieved_chunk_ids") or []
    contested_cited = bool(trace.get("contested_cited"))

    def result(category: str, reason: str, **signals) -> Triage:
        return Triage(
            trace_id=trace_id, category=category, reason=reason,
            query=query, confidence=confidence,
            signals={"action": action, "cache_status": cache_status, **signals},
        )

    # 1. CACHE — checked first because a cache hit means none of the other
    #    stages ran for THIS request. Blaming retrieval for an answer that
    #    retrieval never produced would send you to debug the wrong component
    #    entirely, and a semantic hit is the likeliest culprit: it served an
    #    answer written for a different question.
    if cache_status == "semantic_hit":
        return result(
            CACHE_FAILURE,
            "a semantically similar cached answer was served — check whether the "
            "questions were really the same",
            similarity=trace.get("cache_similarity"),
        )
    if cache_status == "exact_hit":
        return result(
            CACHE_FAILURE,
            "an exact-match cached answer was served — either it was wrong when "
            "cached, or the underlying source changed without invalidation",
        )

    # 2. STALE DATA — a contested or superseded source was used. Checked
    #    before generation because the model may have followed the prompt
    #    perfectly while the CONTEXT was out of date. That is an ingestion
    #    problem wearing a generation problem's clothes.
    if contested_cited:
        return result(
            STALE_DATA,
            "the answer cited a chunk that ingestion flagged as contradicted by a "
            "newer changelog entry (ADR-009) — the conflict rule did not fire",
            contested=True,
        )

    # 3. RETRIEVAL — nothing came back, or what came back scored badly. If the
    #    right chunks never arrived, no prompt could have produced a good
    #    answer, so generation cannot be at fault.
    if not chunk_ids:
        return result(RETRIEVAL_FAILURE, "no chunks were retrieved at all", chunks=0)

    if action == "escalated" and confidence > 0:
        return result(
            RETRIEVAL_FAILURE,
            f"retrieval scored {confidence:.3f}, below the confidence gate — the "
            "system abstained and the user was not satisfied with that",
            chunks=len(chunk_ids),
        )

    # 4. GENERATION — chunks arrived, scored well, and the answer was still
    #    rated bad. Fabricated citations or poor grounding make it explicit;
    #    otherwise it is the residual case.
    if report.get("has_fabricated_citations"):
        return result(
            GENERATION_FAILURE,
            "the answer cited sources that were never offered to it",
            invalid_indices=report.get("invalid_indices"),
        )

    grounding = report.get("grounding_rate")
    if grounding is not None and grounding < 0.6:
        return result(
            GENERATION_FAILURE,
            f"only {grounding:.0%} of claims were supported by their cited sources",
            grounding_rate=grounding,
        )

    if action == "answered" and chunk_ids:
        return result(
            GENERATION_FAILURE,
            "retrieval and grounding both look healthy, so the answer was probably "
            "unhelpful rather than unsupported — read it",
            chunks=len(chunk_ids), grounding_rate=grounding,
        )

    # 5. UNCLEAR — deliberately not forced into a bucket. A misclassified
    #    failure is worse than an unclassified one: it sends someone to fix
    #    the wrong component, and the real bug survives the investigation.
    return result(UNCLEAR, "the trace does not distinguish the failure modes")


def summarize(triaged: list[Triage]) -> dict[str, int]:
    """Counts per category — the number that decides what to work on next."""
    counts: dict[str, int] = {}
    for item in triaged:
        counts[item.category] = counts.get(item.category, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
