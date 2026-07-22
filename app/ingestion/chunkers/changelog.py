"""Entry-level chunker for changelogs (Design.md §4, row 2).

One changelog entry = one chunk. No splitting, no merging.

Why this is the whole algorithm: a changelog entry is already an atomic
unit. Splitting it loses meaning ("increased to 5 attempts" without "webhook
retry limit"); merging entries loses precision — and precision here is
exactly *which version changed what*, which is the entire point of a
changelog for a support system.

Entries are small (50-150 tokens), so the retrieval unit is tight and the
citation a user sees is exactly one release note.

The version + date go into both the chunk TEXT and the metadata:
  - in the text, so the model can state "as of v2.4 (2026-06-10)..." and so
    BM25 can match a query containing "v2.4";
  - in metadata, so retrieval can boost recency (Design.md §3) and the
    conflict rule can compare dates without parsing prose.
"""

from __future__ import annotations

from app.ingestion.chunkers.base import Chunker, register
from app.ingestion.models import ParsedDocument, ProtoChunk


@register
class ChangelogChunker(Chunker):
    source_type = "changelog"

    def chunk(self, document: ParsedDocument) -> list[ProtoChunk]:
        extra = document.extra
        version = document.doc_version or extra.get("version", "unknown")
        date = document.effective_date.isoformat()
        kind = extra.get("kind", "changed")

        # Header line mirrors how a human reads a changelog, and puts the
        # version/date/type into the lexical index for free.
        header = f"Changelog {version} ({date}) — {kind}: {document.title}"
        content = f"{header}\n\n{document.content.strip()}"

        return [
            ProtoChunk(
                chunk_index=0,
                content=content,
                token_count=self.tokens.count(content),
                heading_path=None,  # changelogs are flat: no heading hierarchy
                metadata={
                    "source_type": "changelog",
                    "entry_id": extra.get("entry_id"),
                    "version": version,
                    "kind": kind,
                    "product_area": document.product_area,
                    # Retained so the conflict-detection and stale-data eval
                    # cases can find these chunks by intent, not by string match
                    "supersedes": extra.get("supersedes"),
                    "conflicts_with": extra.get("conflicts_with"),
                },
            )
        ]
