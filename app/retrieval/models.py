"""Shared retrieval types.

These sit between the legs (which know SQL) and the service (which knows the
pipeline), the same way `app/ingestion/models.py` sits between loaders and
the repository. Phase 3's confidence gate and Phase 4's eval harness consume
`RetrievalResult` — so anything a downstream stage needs to make a decision
or to explain itself must be a field here, not a log line.

Design.md §5 (hybrid retrieval), §6 (reranking), §12 (per-stage latency).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

# The three ways to run retrieval. `hybrid` is production; the single-leg
# modes exist so Phase 4's "BM25 vs vector vs hybrid" comparison table is
# produced by THIS code path rather than a second, subtly-different one.
RetrievalMode = Literal["bm25", "vector", "hybrid"]

# Names used as RRF list keys and as weight-config keys. Kept as constants so
# a typo is an ImportError instead of a silently-ignored weight.
LEG_BM25 = "bm25"
LEG_VECTOR = "vector"


class RetrievedChunk(BaseModel):
    """One chunk as retrieval sees it: content plus everything a downstream
    stage needs to cite it, date it, or detect that it is contested.

    Note what is NOT here: the embedding. Nothing after retrieval needs the
    vector, and carrying 384 floats per candidate through the pipeline (and
    into trace payloads) is pure weight.
    """

    chunk_id: str
    document_id: str
    tenant_id: str
    content: str
    heading_path: str | None = None
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Document-level provenance — the citation panel (Phase 6) renders these,
    # and the conflict rule (Design.md §7 rule 4) compares effective_date.
    title: str = ""
    source_type: str = ""
    source_path: str = ""
    doc_version: str | None = None
    effective_date: dt.date | None = None

    @property
    def is_contested(self) -> bool:
        """True when ingestion tagged this chunk as contradicted by a newer
        changelog entry (ADR-009's "unmarked conflict"). Phase 3's prompt
        assembly uses this to make the conflict explicit rather than hoping
        the model notices two dates."""
        return "conflicts_with_entry" in self.metadata


class ScoredChunk(BaseModel):
    """A chunk plus every score and rank it accumulated on its way through
    the pipeline.

    All the score fields are optional because a chunk's history depends on
    which legs found it: a chunk retrieved only by BM25 has no `vector_rank`,
    and that absence is *information* — it means the semantic leg disagreed.
    Storing None rather than 0.0 keeps "not found by this leg" distinct from
    "found by this leg with a terrible score".
    """

    chunk: RetrievedChunk

    # Per-leg evidence. Ranks are 1-based (rank 1 = best), matching RRF's
    # convention and how a human reads a result list.
    bm25_rank: int | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None

    # Fusion output. `fused_score` is the RRF sum; in single-leg modes it is
    # still computed (from one list) so the shape never changes downstream.
    fused_score: float = 0.0
    fused_rank: int = 0

    # Reranker output. None means the reranker did not run — either disabled
    # or skipped by the conditional gate. Downstream MUST distinguish "no
    # rerank score" from "low rerank score"; the confidence gate in Phase 3
    # falls back to fused_score when this is None.
    rerank_score: float | None = None       # sigmoid(logit), 0..1
    rerank_score_raw: float | None = None   # the model's raw logit
    rerank_rank: int | None = None

    @property
    def found_by_both_legs(self) -> bool:
        """Agreement between a lexical and a semantic matcher is the strongest
        cheap relevance signal we have — RRF rewards it arithmetically, and
        the playground displays it."""
        return self.bm25_rank is not None and self.vector_rank is not None

    @property
    def final_score(self) -> float:
        """The score a downstream stage should threshold on.

        Prefers the reranker (a cross-encoder actually read the query and the
        chunk together) and falls back to the fusion score. Centralized here
        so Phase 3's confidence gate and Phase 4's tuning script cannot drift
        apart on what "the score" means.
        """
        return self.rerank_score if self.rerank_score is not None else self.fused_score


class LegResult(BaseModel):
    """What one retrieval leg returned, plus how long it took.

    `error` is set instead of raised when a single leg fails: one broken leg
    degrades hybrid retrieval to single-leg retrieval, which is far better
    than a 500. The service records the degradation; it never hides it.
    """

    leg: str
    chunk_ids: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    elapsed_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class RerankDecision(BaseModel):
    """Why the reranker did or did not run.

    A boolean alone is useless in a trace six weeks later — you need the
    reason and the numbers behind it to tell "correctly skipped, results were
    unambiguous" from "skipped because the margin threshold is miscalibrated".
    """

    reranked: bool
    reason: str                       # 'ambiguous' | 'clear_winner' | 'disabled' | ...
    margin: float | None = None       # (s1 - sN) / s1 over fused scores
    threshold: float | None = None
    candidates_considered: int = 0


class RetrievalResult(BaseModel):
    """Everything one retrieval produced — the unit Phase 3 consumes and
    Phase 4 measures."""

    query: str
    tenant_id: str
    mode: RetrievalMode

    # Ordered best-first. After reranking this is the top-5; without
    # reranking it is the top-K of the fusion.
    results: list[ScoredChunk] = Field(default_factory=list)

    # Full fused candidate list before truncation/reranking. Phase 4's
    # recall@20 needs this, and it is what makes "the reranker demoted the
    # right answer" diagnosable at all.
    candidates: list[ScoredChunk] = Field(default_factory=list)

    legs: list[LegResult] = Field(default_factory=list)
    rerank: RerankDecision | None = None

    # Per-stage timings -> traces.retrieval_ms / rerank_ms (Design.md §12).
    embed_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    total_ms: int = 0

    # Legs that failed and were skipped. Non-empty means the answer was built
    # on less evidence than usual — surfaced, never silently swallowed.
    degraded_legs: list[str] = Field(default_factory=list)

    @property
    def top_score(self) -> float:
        """Score of the best result, or 0.0 when nothing was retrieved.

        This is the number Phase 3's confidence gate compares against its
        abstain threshold. 0.0 for "found nothing" is correct: no evidence
        must never clear a threshold.
        """
        return self.results[0].final_score if self.results else 0.0

    def chunk_ids(self) -> list[str]:
        """Ordered ids — what lands in traces.retrieved_chunk_ids and what the
        golden set's recall metrics compare against."""
        return [scored.chunk.chunk_id for scored in self.results]
