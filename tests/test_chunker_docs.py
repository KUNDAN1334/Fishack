"""Structure-aware docs chunker — the riskiest chunking logic.

Edge cases covered (the project brief calls these out explicitly):
tables, tiny docs, huge sections, heading hierarchies, overlap correctness,
and the model-limit hard cap.

All tests use ApproxTokenCounter so the suite needs no torch.
"""

import pytest

from app.ingestion.chunkers.base import MAX_MODEL_TOKENS, MIN_CHUNK_TOKENS
from app.ingestion.chunkers.docs import DocsChunker, parse_sections, split_blocks
from app.ingestion.models import ParsedDocument
from app.ingestion.tokenizer import ApproxTokenCounter

import datetime as dt


def make_doc(content: str) -> ParsedDocument:
    return ParsedDocument(
        tenant_id="acme", source_type="docs", title="Test Doc",
        source_path="data/raw/acme/docs/test.md", content=content,
        effective_date=dt.date(2026, 5, 1), doc_version="v2.2", product_area="platform",
    )


@pytest.fixture
def chunker():
    return DocsChunker(ApproxTokenCounter())


PARAGRAPH = ("The Flowlytics ingestion pipeline processes events through several stages "
             "before they become queryable in dashboards and reports for customers. ")


# ------------------------------------------------------------- parsing ------

def test_parse_sections_builds_heading_path():
    md = "# Webhooks\n\nintro\n\n## Retry Logic\n\nbody\n\n### Backoff\n\ndetail\n"
    sections = parse_sections(md)
    paths = [path for path, _ in sections]
    assert paths == ["Webhooks", "Webhooks > Retry Logic", "Webhooks > Retry Logic > Backoff"]


def test_parse_sections_strips_frontmatter():
    md = "---\ntitle: X\nslug: y\n---\n\n# Title\n\nbody\n"
    sections = parse_sections(md)
    assert len(sections) == 1
    assert "title: X" not in sections[0][1]


def test_parse_sections_handles_skipped_heading_levels():
    # H1 -> H3 with no H2 must not crash or produce a broken path
    sections = parse_sections("# A\n\ntext\n\n### C\n\nmore\n")
    assert sections[-1][0] == "A > C"


def test_sibling_headings_do_not_nest():
    """Second H2 must be a sibling of the first, not nested under it.

    Note the H1 produces no section here: it has no body text of its own
    (title immediately followed by an H2), and empty sections are dropped
    rather than emitted as content-free chunks.
    """
    md = "# Doc\n\n## First\n\na\n\n## Second\n\nb\n"
    paths = [path for path, _ in parse_sections(md)]
    assert paths == ["Doc > First", "Doc > Second"]


def test_heading_with_body_before_subheading_keeps_its_own_section():
    md = "# Doc\n\nLead paragraph.\n\n## First\n\na\n"
    paths = [path for path, _ in parse_sections(md)]
    assert paths == ["Doc", "Doc > First"]


# -------------------------------------------------------------- blocks ------

def test_split_blocks_keeps_table_whole():
    text = "intro para\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\nafter para"
    blocks = split_blocks(text)
    table_blocks = [b for b in blocks if b.startswith("|")]
    assert len(table_blocks) == 1
    assert "| 3 | 4 |" in table_blocks[0]      # every row in one block
    assert len(blocks) == 3                     # intro, table, after


def test_split_blocks_keeps_code_fence_whole():
    text = "before\n\n```python\nx = 1\n\ny = 2\n```\n\nafter"
    blocks = split_blocks(text)
    fence = [b for b in blocks if b.startswith("```")]
    assert len(fence) == 1
    # The blank line INSIDE the fence must not have split it
    assert "y = 2" in fence[0]


# ------------------------------------------------------------- chunking -----

def test_heading_path_is_prepended_to_content(chunker):
    """ADR-004: the heading path must be inside content (so it reaches both
    the tsvector and the embedding), not only in the metadata column."""
    doc = make_doc("# Webhooks\n\n## Retry Logic\n\n" + PARAGRAPH * 3)
    chunks = chunker.chunk(doc)
    target = [c for c in chunks if c.heading_path == "Webhooks > Retry Logic"][0]
    assert target.content.startswith("Webhooks > Retry Logic")
    assert target.heading_path == "Webhooks > Retry Logic"
    # ...and .body gives the clean text back for display
    assert not target.body.startswith("Webhooks > Retry Logic")


def test_tiny_doc_produces_one_chunk(chunker):
    chunks = chunker.chunk(make_doc("# Tiny\n\nOne short sentence.\n"))
    assert len(chunks) == 1
    assert "One short sentence." in chunks[0].content


def test_empty_doc_produces_no_chunks(chunker):
    assert chunker.chunk(make_doc("---\ntitle: X\n---\n")) == []


def test_huge_section_is_split_with_contiguous_indices(chunker):
    doc = make_doc("# Big\n\n## Huge Section\n\n" + "\n\n".join([PARAGRAPH * 2] * 25))
    chunks = chunker.chunk(doc)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_split_chunks_carry_overlap(chunker):
    """A fact at a boundary must survive in at least one chunk intact."""
    paragraphs = [f"Paragraph {i}. {PARAGRAPH * 2}" for i in range(20)]
    doc = make_doc("# Big\n\n## Section\n\n" + "\n\n".join(paragraphs))
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 2
    # Some paragraph appears in two consecutive chunks (that IS the overlap)
    overlaps = 0
    for first, second in zip(chunks, chunks[1:]):
        for i in range(20):
            marker = f"Paragraph {i}."
            if marker in first.content and marker in second.content:
                overlaps += 1
                break
    assert overlaps >= 1


def test_every_split_chunk_repeats_the_heading_prefix(chunker):
    doc = make_doc("# Doc\n\n## Section\n\n" + "\n\n".join([PARAGRAPH * 2] * 20))
    chunks = chunker.chunk(doc)
    section_chunks = [c for c in chunks if c.heading_path == "Doc > Section"]
    assert len(section_chunks) > 1
    assert all(c.content.startswith("Doc > Section") for c in section_chunks)


def test_no_chunk_exceeds_model_token_limit(chunker):
    """Silent truncation at the embedding model is the worst ingestion bug —
    assert the hard cap holds even for pathological input."""
    wall_of_text = "word " * 6000  # no paragraph breaks at all
    doc = make_doc(f"# Doc\n\n## Wall\n\n{wall_of_text}")
    chunks = chunker.chunk(doc)
    assert chunks
    assert all(c.token_count <= MAX_MODEL_TOKENS + 20 for c in chunks), \
        [c.token_count for c in chunks]


def test_giant_table_is_not_split_when_it_fits(chunker):
    rows = "\n".join(f"| ERR_{i:03d} | 4{i:02d} | Meaning {i} |" for i in range(12))
    table = f"| Code | Status | Meaning |\n|---|---|---|\n{rows}"
    doc = make_doc(f"# Doc\n\n## Errors\n\nIntro paragraph.\n\n{table}\n")
    chunks = chunker.chunk(doc)
    holding = [c for c in chunks if "ERR_000" in c.content]
    assert len(holding) == 1
    assert "ERR_011" in holding[0].content   # first and last row together


def test_small_sibling_sections_are_merged(chunker):
    """Stub sections have no standalone value; they merge under a shared parent."""
    doc = make_doc("# Doc\n\n## Parent\n\n### A\n\nShort a.\n\n### B\n\nShort b.\n")
    chunks = chunker.chunk(doc)
    assert len(chunks) < 3
    combined = " ".join(c.content for c in chunks)
    assert "Short a." in combined and "Short b." in combined


def test_unrelated_small_sections_are_not_merged(chunker):
    """Merging across unrelated H1 branches would put two topics in one chunk."""
    doc = make_doc("# Alpha\n\nShort alpha text.\n\n# Beta\n\nShort beta text.\n")
    chunks = chunker.chunk(doc)
    assert len(chunks) == 2


def test_metadata_carries_version_and_area(chunker):
    chunks = chunker.chunk(make_doc("# Doc\n\n## S\n\n" + PARAGRAPH))
    assert chunks[0].metadata["doc_version"] == "v2.2"
    assert chunks[0].metadata["product_area"] == "platform"
    assert chunks[0].metadata["source_type"] == "docs"


def test_min_chunk_constant_is_below_max():
    from app.ingestion.chunkers.base import MAX_CHUNK_TOKENS, TARGET_CHUNK_TOKENS
    assert MIN_CHUNK_TOKENS < TARGET_CHUNK_TOKENS < MAX_CHUNK_TOKENS <= MAX_MODEL_TOKENS + 20
