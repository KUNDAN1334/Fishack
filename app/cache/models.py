"""What a cached answer stores.

Deliberately NOT the whole `ChatResponse`. A cache entry is a durable copy of
a past answer, and copying every field would mean:

  * storing the full retrieval result (20 chunks of text) per entry, so the
    cache becomes a second copy of the corpus;
  * replaying stale per-request numbers — the original trace_id, latencies and
    token counts — into a new request, which would corrupt /stats. A cache hit
    took 4ms and cost nothing; reporting the original 3,200ms and $0.0004
    would make the dashboard describe a request that did not happen.

So: enough to reconstruct a useful response, plus the chunk ids that make
invalidation possible.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.generation.models import Citation, CitationReport


class CachedAnswer(BaseModel):
    """One cached answer, as stored in Redis."""

    query: str                      # the ORIGINAL query, for debugging a bad hit
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    citation_report: CitationReport | None = None
    confidence: float = 0.0

    # Which chunks this answer was built on. The reverse index (ADR-025) uses
    # these to decide what to delete when a document changes — without them,
    # active invalidation is impossible and you are back to TTL-only.
    chunk_ids: list[str] = Field(default_factory=list)

    # Provenance of the ORIGINAL generation. Kept for debugging ("which model
    # wrote this cached answer?") and explicitly NOT replayed into the new
    # response's cost figures.
    provider: str | None = None
    model: str | None = None
    original_cost_usd: float = 0.0
    cached_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    # Populated only on the semantic path: how close the new query was to the
    # cached one. Lands on the trace so a bad hit can be diagnosed — "0.951,
    # just over the line" is a very different story from "0.998".
    similarity: float | None = None

    def age_seconds(self) -> float:
        return (dt.datetime.now(dt.timezone.utc) - self.cached_at).total_seconds()


class SemanticEntry(BaseModel):
    """A cached answer plus the query embedding used to match against it."""

    entry_id: str
    embedding: list[float]
    answer: CachedAnswer
