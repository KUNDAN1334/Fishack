"""The naive fixed-size chunker — the Phase 4 experiment's control arm.

This is deliberately the chunking strategy Design.md §4 argues against: one
splitter for every source type, fixed character windows, no heading awareness,
no version metadata, no respect for tables or code fences or entry boundaries.

It exists to be BEATEN, and to be beaten by a measurable number. "Per-source
chunking is better" is an assertion; "per-source chunking improves recall@5 by
N points, concentrated in the identifier and stale-conflict case types" is
evidence, and it is the artifact the README's before/after table is built from.

It is a faithful naive baseline, not a strawman. It does what a competent
developer writing their first RAG pipeline does on day one:

  * fixed-size windows with a fixed overlap, measured in CHARACTERS because
    that is what `len()` gives you;
  * split on paragraph boundaries where convenient, mid-word where not;
  * the same treatment for a docs page, a changelog entry and a support ticket.

What it therefore destroys, and what the experiment should show up as lost
recall:

  1. Heading context. A chunk reading "Retries follow exponential backoff, up
     to 3 attempts" contains neither "webhook" nor "retry logic", so a query
     for "webhook retry limit" has almost no lexical OR semantic overlap with
     it (ADR-004).
  2. Changelog atomicity. One entry per chunk is the only reason a changelog
     is useful — split it and "which version changed what" is gone; merge two
     and the version numbers cross-contaminate.
  3. Q&A pairing. A ticket's value is question-plus-resolution together. Cut
     between them and you retrieve a customer complaint with no answer, or an
     answer with no indication of what it answers.

NOT REGISTERED in CHUNKER_REGISTRY on purpose. `get_chunker()` must never
return this by accident — it is selected explicitly by the experiment script
and by nothing else.
"""

from __future__ import annotations

from app.ingestion.chunkers.base import Chunker
from app.ingestion.models import ParsedDocument, ProtoChunk

# ~4 chars per token, so 1600 chars ≈ 400 tokens — the same size band the
# structure-aware chunker targets. That is the point: the experiment must
# isolate STRATEGY, not size. A naive chunker that also used the wrong size
# would confound the two and the result would prove nothing.
NAIVE_CHUNK_CHARS = 1600
NAIVE_OVERLAP_CHARS = 240  # ~15%, matching OVERLAP_TOKENS


class NaiveChunker(Chunker):
    """Fixed-size character windows, one strategy for every source."""

    source_type = "naive"

    def chunk(self, document: ParsedDocument) -> list[ProtoChunk]:
        text = document.content.strip()
        if not text:
            return []

        windows = _split_fixed(text, NAIVE_CHUNK_CHARS, NAIVE_OVERLAP_CHARS)

        return [
            ProtoChunk(
                chunk_index=index,
                content=window,
                token_count=self.tokens.count(window),
                # No heading path — the naive chunker does not parse headings.
                # This absence IS the experiment's subject.
                heading_path=None,
                # DOCUMENT-level metadata is carried, chunk-level is not.
                #
                # This distinction took a broken experiment to get right. The
                # first version carried almost nothing, so ticket and changelog
                # locators could not resolve against the naive corpus at all —
                # only 8 of 41 cases scored, and the "comparison" was 8 cases
                # against 41. Not a comparison.
                #
                # The fix is not a hack, it is the correct model of the
                # baseline: a naive chunker is naive about SPLITTING, not
                # about PROVENANCE. Any real first-attempt pipeline still
                # knows which ticket a chunk came from — that comes from the
                # loader, not from parsing structure. Withholding it would
                # make the baseline a strawman and would confound "worse
                # chunking" with "worse metadata".
                #
                # What it still cannot have: heading_path, and anything that
                # requires understanding the document's internal structure.
                metadata={
                    "source_type": document.source_type,
                    "doc_version": document.doc_version,
                    "product_area": document.product_area,
                    "chunking": "naive_fixed",
                    **{
                        key: value
                        for key, value in document.extra.items()
                        if key in ("ticket_id", "entry_id", "error_code",
                                   "resolution_tag", "version", "kind")
                    },
                },
            )
            for index, window in enumerate(windows)
        ]


def _split_fixed(text: str, size: int, overlap: int) -> list[str]:
    """Fixed-size windows with a fixed overlap.

    One concession to competence: the window end is nudged back to the nearest
    paragraph or sentence boundary when one is close by, because splitting
    mid-word is a strawman nobody would actually ship. The concession makes
    the baseline HARDER to beat, which is the right direction — an experiment
    that only wins against an incompetent control has not demonstrated much.

    Pure function so the windowing is testable without a document, a
    tokenizer, or a database.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size, or the loop cannot advance")

    windows: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + size, length)

        if end < length:
            # Look back over the last 20% of the window for a clean break.
            search_from = start + int(size * 0.8)
            paragraph = text.rfind("\n\n", search_from, end)
            if paragraph != -1:
                end = paragraph
            else:
                sentence = text.rfind(". ", search_from, end)
                if sentence != -1:
                    end = sentence + 1

        window = text[start:end].strip()
        if window:
            windows.append(window)

        if end >= length:
            break
        # Advance by size-minus-overlap from the ACTUAL end, so a window that
        # was shortened to hit a boundary does not silently lose its overlap.
        start = max(start + 1, end - overlap)

    return windows
