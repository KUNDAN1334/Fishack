"""Types for the generation path.

Sits between retrieval (which produces `ScoredChunk`) and the API (which
serializes to SSE). Every field a downstream stage needs to make a decision or
explain itself lives here rather than in a log line — the same rule as
`app/retrieval/models.py`.

Design.md §2 (the request lifecycle), §7 (citations), §12 (observability).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.retrieval.models import RetrievalResult, ScoredChunk

# What the pipeline decided to do. Mirrors the CHECK constraint on
# traces.action so a value that cannot be stored cannot be produced.
Action = Literal["answered", "abstained", "escalated", "cache_hit"]


class Turn(BaseModel):
    """One prior message in the conversation.

    The client sends these; the server stores none of them (ADR-003). They are
    an INPUT to query rewriting, not server state.
    """

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """One question, with whatever context the client chose to send."""

    tenant_id: str
    query: str
    # Prior turns, oldest first. Empty on the first turn of a conversation,
    # which is exactly when query rewriting is skipped.
    messages: list[Turn] = Field(default_factory=list)
    # Client-generated, so the server stays stateless. Lands on the trace row
    # so turns can be grouped in observability and in the golden set's
    # multi-turn cases (ADR-003).
    conversation_id: str | None = None


class Citation(BaseModel):
    """One numbered source offered to the model, and whether it was used.

    `index` is the [n] the model sees. It is 1-based because that is what
    reads naturally in an answer, and off-by-one here would mean every
    citation in the product points one source too far.
    """

    index: int
    chunk_id: str
    document_id: str
    title: str
    source_type: str
    source_path: str
    heading_path: str | None = None
    doc_version: str | None = None
    effective_date: dt.date | None = None
    # Retrieval's own opinion, carried through so the UI can show why this
    # source was offered at all.
    score: float = 0.0
    # True when ingestion flagged this chunk as contradicted by a newer
    # changelog entry (ADR-009). The prompt makes this explicit rather than
    # hoping the model compares dates on its own.
    is_contested: bool = False
    # Set during validation: did the answer actually cite this source?
    was_cited: bool = False


class ClaimCheck(BaseModel):
    """One sentence of the answer, checked against the source it cited."""

    claim: str
    cited_indices: list[int] = Field(default_factory=list)
    # Best similarity between this claim and any chunk it cited. None when the
    # claim cited nothing at all.
    similarity: float | None = None
    supported: bool = False
    problem: str | None = None  # 'uncited' | 'unknown_source' | 'weak_support'


class CitationReport(BaseModel):
    """The post-hoc verdict on an answer's citations (Design.md §7).

    Note what this is NOT: a claim that the answer is correct. It says the
    cited chunks are topically consistent with the sentences citing them.
    Similarity cannot catch a citation that says the opposite of the claim —
    that needs entailment. Named `similarity` throughout rather than
    `entailment` so the limitation is visible at every call site.
    """

    claims: list[ClaimCheck] = Field(default_factory=list)
    # Citation markers pointing at a source number we never offered — the
    # clearest possible evidence of fabrication, and the reason to parse
    # markers rather than trust them.
    invalid_indices: list[int] = Field(default_factory=list)
    # Sources offered to the model that the answer never used. Not a problem
    # in itself; a useful retrieval-precision signal in aggregate.
    unused_indices: list[int] = Field(default_factory=list)

    @property
    def total_claims(self) -> int:
        return len(self.claims)

    @property
    def unsupported_claims(self) -> list[ClaimCheck]:
        return [claim for claim in self.claims if not claim.supported]

    @property
    def has_fabricated_citations(self) -> bool:
        """A marker pointing at a source that does not exist. Distinct from a
        weakly-supported claim: this one is unambiguous."""
        return bool(self.invalid_indices)

    @property
    def grounding_rate(self) -> float:
        """Fraction of claims whose citation checks out. 1.0 when the answer
        made no factual claims at all (an abstention), which is correct — an
        abstention is perfectly grounded."""
        if not self.claims:
            return 1.0
        return sum(1 for claim in self.claims if claim.supported) / len(self.claims)


class GateDecision(BaseModel):
    """Why the pipeline did or did not call the LLM.

    Design.md §7 technique 5 puts this BEFORE generation, which makes it the
    only anti-hallucination control that works by not running the model — it
    saves the cost as well as the risk.
    """

    should_generate: bool
    reason: str          # 'confident' | 'no_results' | 'below_threshold' | ...
    top_score: float = 0.0
    threshold: float = 0.0
    # Which scale the comparison used — 'rerank' (0-1 sigmoid) or 'fused'
    # (RRF). They differ by ~30x, so a decision is uninterpretable without it.
    score_kind: str = "fused"


class RewriteResult(BaseModel):
    """What query rewriting did, if anything."""

    original: str
    rewritten: str
    changed: bool = False
    skipped_reason: str | None = None   # 'first_turn' | 'disabled' | 'failed'
    elapsed_ms: int = 0

    @property
    def effective_query(self) -> str:
        return self.rewritten or self.original


class ChatResponse(BaseModel):
    """The complete result of one chat request.

    Assembled incrementally during streaming and emitted whole in the final
    SSE event, so the client gets citations and the validation report after
    the text it already rendered.
    """

    answer: str = ""
    action: Action = "answered"
    tenant_id: str = ""
    conversation_id: str | None = None
    trace_id: str | None = None

    citations: list[Citation] = Field(default_factory=list)
    citation_report: CitationReport | None = None
    gate: GateDecision | None = None
    rewrite: RewriteResult | None = None
    escalation_id: str | None = None

    # Observability (Design.md §12). Duplicated onto the response, not just
    # the trace row, because the playground and the Phase 6 UI both show them
    # and neither should have to query Postgres to do it.
    confidence: float = 0.0
    provider: str | None = None
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    virtual_cost_usd: float = 0.0
    failover_events: list[dict] = Field(default_factory=list)
    rewrite_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    generation_ms: int = 0
    validation_ms: int = 0
    total_ms: int = 0
    degraded_legs: list[str] = Field(default_factory=list)

    # Kept off the wire but used by the pipeline and the playground.
    retrieval: RetrievalResult | None = Field(default=None, exclude=True)

    @property
    def is_abstention(self) -> bool:
        return self.action in ("abstained", "escalated")


class StreamChunk(BaseModel):
    """One SSE event.

    Three types, in this order over the wire:
      'meta'  — sent BEFORE any text: citations and the gate decision, so the
                UI can render the sources panel while the answer types out.
      'delta' — a fragment of the answer.
      'final' — the complete ChatResponse, including the citation report,
                which by definition cannot exist until the answer does.
    """

    type: Literal["meta", "delta", "final", "error"]
    text: str = ""
    data: dict[str, Any] | None = None


def build_citations(results: list[ScoredChunk]) -> list[Citation]:
    """Number the retrieved chunks 1..N — the mapping the whole citation
    system rests on.

    Done once, here, and passed to both the prompt builder and the validator.
    If those two ever numbered the sources independently they could drift, and
    every citation in the product would silently point at the wrong document
    while looking perfectly healthy.
    """
    citations = []
    for index, scored in enumerate(results, start=1):
        chunk = scored.chunk
        citations.append(
            Citation(
                index=index,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                source_type=chunk.source_type,
                source_path=chunk.source_path,
                heading_path=chunk.heading_path,
                doc_version=chunk.doc_version,
                effective_date=chunk.effective_date,
                score=scored.final_score,
                is_contested=chunk.is_contested,
            )
        )
    return citations
