"""Changelog and ticket chunkers + the registry.

These strategies are simple by design; the tests pin the properties that
make them CORRECT: atomicity, exact-identifier presence, and metadata that
downstream phases depend on.
"""

import datetime as dt

import pytest

from app.ingestion.chunkers import get_chunker
from app.ingestion.chunkers.changelog import ChangelogChunker
from app.ingestion.chunkers.tickets import TicketChunker
from app.ingestion.models import ParsedDocument
from app.ingestion.tokenizer import ApproxTokenCounter


@pytest.fixture
def counter():
    return ApproxTokenCounter()


def changelog_doc(**extra) -> ParsedDocument:
    return ParsedDocument(
        tenant_id="acme", source_type="changelog",
        title="Webhook retry limit increased to 5 attempts",
        source_path="data/raw/acme/changelog.jsonl#CL-2026-0610-01",
        content="Webhook retries now attempt up to 5 times instead of 3.",
        effective_date=dt.date(2026, 6, 10), doc_version="v2.4", product_area="platform",
        extra={"entry_id": "CL-2026-0610-01", "kind": "changed", "version": "v2.4", **extra},
    )


def ticket_doc(question: str = "Short question.", answer: str = "Short answer.") -> ParsedDocument:
    return ParsedDocument(
        tenant_id="acme", source_type="ticket", title="Webhooks failing after upgrade",
        source_path="data/raw/acme/tickets.jsonl#ACM-1041",
        content=f"{question}\n\n{answer}",
        effective_date=dt.date(2026, 5, 3), product_area="platform",
        extra={"ticket_id": "ACM-1041", "question": question, "answer": answer,
               "resolution_tag": "config", "error_code": "ERR_TIMEOUT_502"},
    )


# ---------------------------------------------------------- changelog ------

def test_changelog_entry_is_exactly_one_chunk(counter):
    chunks = ChangelogChunker(counter).chunk(changelog_doc())
    assert len(chunks) == 1


def test_changelog_chunk_contains_version_and_date(counter):
    """Version/date must be in the TEXT (for BM25 + the model's conflict
    rule), not only in metadata."""
    chunk = ChangelogChunker(counter).chunk(changelog_doc())[0]
    assert "v2.4" in chunk.content
    assert "2026-06-10" in chunk.content
    assert chunk.metadata["version"] == "v2.4"


def test_changelog_carries_conflict_pointers(counter):
    chunk = ChangelogChunker(counter).chunk(
        changelog_doc(supersedes="data-export", conflicts_with="webhooks-overview")
    )[0]
    assert chunk.metadata["supersedes"] == "data-export"
    assert chunk.metadata["conflicts_with"] == "webhooks-overview"


def test_changelog_has_no_heading_path(counter):
    assert ChangelogChunker(counter).chunk(changelog_doc())[0].heading_path is None


# ------------------------------------------------------------- tickets -----

def test_ticket_qa_pair_stays_together(counter):
    chunk = TicketChunker(counter).chunk(ticket_doc())[0]
    assert "Customer question:" in chunk.content
    assert "Resolution:" in chunk.content


def test_ticket_error_code_appears_verbatim(counter):
    """The exact-identifier case: BM25 must be able to match ERR_TIMEOUT_502."""
    chunk = TicketChunker(counter).chunk(ticket_doc())[0]
    assert "ERR_TIMEOUT_502" in chunk.content
    assert chunk.metadata["error_code"] == "ERR_TIMEOUT_502"


def test_long_ticket_splits_at_qa_boundary(counter):
    long_text = "Detailed explanation of the failure mode. " * 80
    chunks = TicketChunker(counter).chunk(ticket_doc(question=long_text, answer=long_text))
    assert len(chunks) == 2
    assert chunks[0].metadata["part"] == "question"
    assert chunks[1].metadata["part"] == "answer"
    # Each half still identifies its ticket AND its error code standalone
    for chunk in chunks:
        assert "ACM-1041" in chunk.content
        assert "ERR_TIMEOUT_502" in chunk.content


def test_ticket_indices_are_contiguous(counter):
    long_text = "text " * 500
    chunks = TicketChunker(counter).chunk(ticket_doc(question=long_text, answer=long_text))
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# ------------------------------------------------------------ registry -----

def test_registry_returns_the_right_strategy_per_source(counter):
    assert type(get_chunker("docs", counter)).__name__ == "DocsChunker"
    assert type(get_chunker("changelog", counter)).__name__ == "ChangelogChunker"
    assert type(get_chunker("ticket", counter)).__name__ == "TicketChunker"


def test_unknown_source_type_raises_loudly(counter):
    """Silently defaulting to naive chunking for a new source is exactly the
    production mistake Design.md §4 warns about."""
    with pytest.raises(ValueError, match="No chunker registered"):
        get_chunker("slack", counter)
