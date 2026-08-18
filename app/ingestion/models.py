"""Shared ingestion types.

These sit between loaders (which know file formats) and the repository
(which knows SQL). Chunkers consume ParsedDocument and emit ProtoChunk;
neither layer knows about the other's concerns.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    """One source document, format-agnostic, before chunking."""

    tenant_id: str
    source_type: str            # 'docs' | 'changelog' | 'ticket'
    title: str
    source_path: str            # provenance, relative to repo root
    content: str                # raw body used for hashing + chunking
    effective_date: dt.date
    doc_version: str | None = None
    product_area: str | None = None
    # Source-specific extras the chunker needs (changelog kind, ticket
    # question/answer split, supersedes targets...). Kept loose on purpose:
    # each source has different fields and forcing one schema would mean a
    # union type with mostly-None columns.
    extra: dict[str, Any] = Field(default_factory=dict)


class ProtoChunk(BaseModel):
    """A chunk after splitting, before embedding and persistence.

    `content` is exactly what gets embedded AND what lands in the tsvector —
    for docs chunks it already carries the heading-path prefix (ADR-004).
    """

    chunk_index: int
    content: str
    token_count: int
    heading_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def body(self) -> str:
        """Content with the heading prefix stripped — for UI display.

        The prefix helps retrieval but is noise when showing a citation to a
        human, who already sees the heading path as a separate field.
        """
        if self.heading_path and self.content.startswith(self.heading_path):
            return self.content[len(self.heading_path):].lstrip("\n")
        return self.content


class IngestionResult(BaseModel):
    """Per-run summary printed by the CLI and asserted in tests."""

    documents_ingested: int = 0
    documents_skipped_duplicate: int = 0
    documents_superseded: int = 0
    chunks_written: int = 0
    embeddings_computed: int = 0
    embeddings_from_cache: int = 0
    # Cached ANSWERS evicted because their source chunks changed (Phase 5,
    # ADR-025). Reported by the CLI so an operator can see that a re-ingest
    # actually took effect for users, not just in the database.
    cache_entries_invalidated: int = 0
    errors: list[str] = Field(default_factory=list)

    def merge(self, other: IngestionResult) -> None:
        self.documents_ingested += other.documents_ingested
        self.documents_skipped_duplicate += other.documents_skipped_duplicate
        self.documents_superseded += other.documents_superseded
        self.chunks_written += other.chunks_written
        self.embeddings_computed += other.embeddings_computed
        self.embeddings_from_cache += other.embeddings_from_cache
        self.cache_entries_invalidated += other.cache_entries_invalidated
        self.errors.extend(other.errors)
