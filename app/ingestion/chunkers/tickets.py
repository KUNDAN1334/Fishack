"""Conversation-level chunker for resolved support tickets (Design.md §4, row 3).

One resolved ticket (question + accepted answer) = one chunk.

Why keep the pair together: "Ticket ka value uske Q&A pair me hai" — the
question carries the user's vocabulary (how real customers phrase the
problem, which is what future queries will look like) and the answer carries
the resolution. Split them and you get chunks that either describe a problem
with no fix, or a fix with no indication of what it fixes. Both are useless
to retrieve.

Long tickets (>MAX_CHUNK_TOKENS) split at the Q/A boundary rather than
mid-text, and each half is labelled so it still reads as part of a ticket.
"""

from __future__ import annotations

from app.ingestion.chunkers.base import MAX_CHUNK_TOKENS, Chunker, register
from app.ingestion.models import ParsedDocument, ProtoChunk


@register
class TicketChunker(Chunker):
    source_type = "ticket"

    def chunk(self, document: ParsedDocument) -> list[ProtoChunk]:
        extra = document.extra
        ticket_id = extra.get("ticket_id", "unknown")
        question = (extra.get("question") or "").strip()
        answer = (extra.get("answer") or "").strip()
        error_code = extra.get("error_code")

        # The error code is repeated in the header line even though it also
        # appears in the body: exact-identifier queries ("ERR_TIMEOUT_502")
        # are the case where BM25 must win (Design.md §5), so we make sure the
        # token is unambiguously present and near the top of the chunk.
        header_bits = [f"Support ticket {ticket_id}: {document.title}"]
        if error_code:
            header_bits.append(f"Error code: {error_code}")
        if document.product_area:
            header_bits.append(f"Product area: {document.product_area}")
        header = " | ".join(header_bits)

        full = f"{header}\n\nCustomer question:\n{question}\n\nResolution:\n{answer}"
        base_metadata = {
            "source_type": "ticket",
            "ticket_id": ticket_id,
            "product_area": document.product_area,
            "resolution_tag": extra.get("resolution_tag"),
            "error_code": error_code,
        }

        if self.tokens.count(full) <= MAX_CHUNK_TOKENS:
            return [
                ProtoChunk(
                    chunk_index=0,
                    content=full,
                    token_count=self.tokens.count(full),
                    metadata=base_metadata,
                )
            ]

        # Too long: split at the natural Q/A seam. Each part repeats the
        # header so a retrieved half still identifies its ticket and error
        # code — a chunk must always be interpretable standalone.
        parts = [
            f"{header}\n\nCustomer question:\n{question}",
            f"{header}\n\nResolution:\n{answer}",
        ]
        return [
            ProtoChunk(
                chunk_index=index,
                content=part,
                token_count=self.tokens.count(part),
                metadata={**base_metadata, "part": "question" if index == 0 else "answer"},
            )
            for index, part in enumerate(parts)
        ]
