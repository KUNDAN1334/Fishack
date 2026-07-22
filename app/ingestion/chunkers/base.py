"""Chunker interface, shared sizing constants, and the registry.

All the thresholds that define "a good chunk" live here with their
rationale, so the Phase 4 chunking experiment has one place to vary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.ingestion.models import ParsedDocument, ProtoChunk
from app.ingestion.tokenizer import TokenCounter

# ---------------------------------------------------------------------------
# Sizing constants (Design.md §4 "medium chunks 300-500 tokens + 10-15% overlap")
# ---------------------------------------------------------------------------

# Target ceiling for a docs chunk. Above this, precision drops (the LLM gets a
# needle-in-haystack problem) and citations become less useful to a human.
MAX_CHUNK_TOKENS = 500

# Below this, a chunk usually lacks the context to stand alone as an answer,
# so small trailing sections get merged with their neighbour instead.
MIN_CHUNK_TOKENS = 120

# Where we aim to split when a section must be divided.
TARGET_CHUNK_TOKENS = 400

# 15% of TARGET (Design.md §4 says 10-15%). Overlap exists so a fact that
# straddles a boundary survives in at least one chunk intact. Costs ~15% more
# storage and slightly inflates recall metrics (the same text is findable
# twice) — a tradeoff we accept and document.
OVERLAP_TOKENS = 60

# bge-small truncates at 512. We keep a safety margin below it so special
# tokens and any downstream prefixing can never push a chunk into silent
# truncation. Anything above this is hard-split regardless of structure.
MAX_MODEL_TOKENS = 480


class Chunker(ABC):
    """Turns one ParsedDocument into an ordered list of ProtoChunks."""

    source_type: str = "base"

    def __init__(self, token_counter: TokenCounter):
        self.tokens = token_counter

    @abstractmethod
    def chunk(self, document: ParsedDocument) -> list[ProtoChunk]:
        """Split `document`. Must return chunks with contiguous chunk_index
        starting at 0 (the DB has UNIQUE(document_id, chunk_index))."""


CHUNKER_REGISTRY: dict[str, type[Chunker]] = {}


def register(cls: type[Chunker]) -> type[Chunker]:
    """Decorator: register a chunker under its source_type."""
    CHUNKER_REGISTRY[cls.source_type] = cls
    return cls


def get_chunker(source_type: str, token_counter: TokenCounter) -> Chunker:
    """Look up the strategy for a source type.

    Unknown types raise rather than silently falling back to a default —
    a new source with accidentally-naive chunking is exactly the production
    mistake Design.md §4 warns about.
    """
    # Imports here (not at module top) to avoid a circular import: the
    # concrete chunkers import this module for the registry decorator.
    from app.ingestion.chunkers import changelog, docs, tickets  # noqa: F401

    if source_type not in CHUNKER_REGISTRY:
        raise ValueError(
            f"No chunker registered for source_type={source_type!r}. "
            f"Known: {sorted(CHUNKER_REGISTRY)}"
        )
    return CHUNKER_REGISTRY[source_type](token_counter)
