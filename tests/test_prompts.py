"""Prompt assembly (Design.md §7).

Prompts are the part of a RAG system most likely to be edited under pressure,
so the properties the rest of the pipeline DEPENDS ON are pinned here. Not the
wording — that will change — but the structure: rules before context, the
abstention sentence present verbatim, dates on every source, contested chunks
flagged, and the numbering aligned with what the validator will check against.
"""

import datetime as dt

import pytest

from app.generation.models import Citation, Turn, build_citations
from app.generation.prompts import (
    FEW_SHOT_EXAMPLES,
    build_context_block,
    build_messages,
    build_rewrite_messages,
)
from app.retrieval.models import RetrievedChunk, ScoredChunk

ABSTENTION = (
    "I don't have enough information to answer this confidently. "
    "I'm escalating this to a human agent."
)


def chunk(
    chunk_id="c1", *, content="Webhook deliveries retry up to 3 times.",
    heading="Webhooks > Retry Logic", title="Webhooks Overview",
    version="v2.2", date=dt.date(2026, 3, 12), contested=False, source="docs",
) -> ScoredChunk:
    metadata = {"conflicts_with_entry": "CL-2026-0610-01"} if contested else {}
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=chunk_id, document_id=f"d-{chunk_id}", tenant_id="acme",
            content=f"{heading}\n\n{content}" if heading else content,
            heading_path=heading, metadata=metadata, title=title,
            source_type=source, source_path="webhooks.md",
            doc_version=version, effective_date=date,
        ),
        fused_score=0.03, rerank_score=0.8,
    )


# ------------------------------------------------------------- numbering --


def test_citations_are_numbered_from_one_in_retrieval_order():
    """1-based because that is what reads naturally in an answer — and an
    off-by-one here would make every citation in the product point one source
    too far."""
    results = [chunk("a"), chunk("b"), chunk("c")]
    citations = build_citations(results)

    assert [c.index for c in citations] == [1, 2, 3]
    assert [c.chunk_id for c in citations] == ["a", "b", "c"]


def test_numbering_is_computed_once_and_shared():
    """The prompt builder and the validator must use the SAME mapping. If they
    numbered sources independently they could drift, and every citation would
    silently point at the wrong document while looking healthy."""
    results = [chunk("a"), chunk("b")]
    citations = build_citations(results)
    block = build_context_block(citations, results)

    assert "[1]" in block and "[2]" in block
    assert citations[0].chunk_id == "a"


def test_contested_flag_is_carried_from_ingestion_metadata():
    citations = build_citations([chunk("a", contested=True)])
    assert citations[0].is_contested is True


# --------------------------------------------------------- source blocks --


def test_every_source_carries_its_date():
    """Rule 4 says prefer the more recent source. That is impossible to follow
    if the model cannot see which IS more recent — the single most common way
    the conflict rule fails in practice."""
    results = [chunk("a", version="v2.2", date=dt.date(2026, 3, 12))]
    block = build_context_block(build_citations(results), results)

    assert "v2.2" in block
    assert "2026-03-12" in block


def test_contested_sources_are_flagged_in_the_prompt():
    """Ingestion already worked out that a newer changelog contradicts this
    chunk (ADR-009). Saying so is cheaper and more reliable than hoping the
    model compares two dates on its own."""
    results = [chunk("a", contested=True)]
    block = build_context_block(build_citations(results), results)

    assert "newer changelog entry contradicts" in block


def test_source_body_excludes_the_heading_prefix():
    """ADR-004 prepends the heading path into chunk content for retrieval. The
    prompt shows the heading in the header line instead, so repeating it in
    the body would waste tokens on every single source."""
    results = [chunk("a", heading="Webhooks > Retry Logic", content="Retries cap at 3.")]
    block = build_context_block(build_citations(results), results)

    assert block.count("Webhooks > Retry Logic") == 1


# -------------------------------------------------------------- messages --


def test_rules_come_before_context_and_the_question_comes_last():
    """Models attend most reliably to the start and end of a prompt. Rules
    first, question last, bulk of the context between them. Putting the
    question first leaves the rules competing with 2000 tokens of context."""
    results = [chunk("a")]
    messages = build_messages(
        "How many retries?", build_citations(results), results,
        abstention_message=ABSTENTION,
    )

    assert messages[0].role == "system"
    assert "RULES:" in messages[0].content
    assert messages[-1].role == "user"
    assert messages[-1].content.rstrip().endswith("How many retries?")
    assert "SOURCES:" in messages[-1].content


def test_the_abstention_sentence_appears_verbatim_in_the_system_prompt():
    """Three things must agree on this string: the prompt tells the model to
    emit it, the generator detects it to set action='abstained', and Phase 4
    asserts on it. It lives in config for exactly that reason."""
    results = [chunk("a")]
    messages = build_messages(
        "q", build_citations(results), results, abstention_message=ABSTENTION
    )
    assert ABSTENTION in messages[0].content


def test_todays_date_is_stated_so_recency_is_anchorable():
    results = [chunk("a")]
    messages = build_messages(
        "q", build_citations(results), results,
        abstention_message=ABSTENTION, today=dt.date(2026, 8, 1),
    )
    assert "2026-08-01" in messages[0].content


def test_few_shot_examples_are_real_turns_not_prose():
    """An example inside a system prompt is something to read; an example in
    the message history is something to imitate. Instruction-tuned models were
    trained on the second."""
    results = [chunk("a")]
    messages = build_messages(
        "q", build_citations(results), results, abstention_message=ABSTENTION
    )
    roles = [m.role for m in messages]

    assert roles.count("assistant") == len(FEW_SHOT_EXAMPLES)
    assert roles[1] == "user" and roles[2] == "assistant"


def test_few_shot_set_covers_abstain_conflict_and_normal():
    """Abstention examples alone bias the model toward over-abstaining — the
    failure you create while fixing the other one. The positive example is
    load-bearing, not decoration."""
    assert len(FEW_SHOT_EXAMPLES) == 3
    rendered = " ".join(a for _, a in FEW_SHOT_EXAMPLES)
    assert "{abstention}" in rendered          # the abstain case
    assert "out of date" in rendered            # the conflict case
    assert "HTTP 429" in rendered               # the normal case


def test_few_shot_can_be_disabled():
    results = [chunk("a")]
    messages = build_messages(
        "q", build_citations(results), results,
        abstention_message=ABSTENTION, include_few_shot=False,
    )
    assert [m.role for m in messages] == ["system", "user"]


def test_history_is_included_without_its_old_sources():
    """Re-injecting earlier turns' context would let the model answer turn 3
    from turn 1's chunks — and its citation markers would then refer to
    sources absent from the current numbering, which validation would report
    as fabricated. A genuinely nasty grounding bug."""
    results = [chunk("a")]
    history = [
        Turn(role="user", content="Why is my webhook failing?"),
        Turn(role="assistant", content="Deliveries retry up to 3 times [1]."),
    ]
    # Few-shot examples legitimately contain their own SOURCES blocks, so
    # they are excluded here to isolate the property under test.
    messages = build_messages(
        "what about the backoff?", build_citations(results), results,
        abstention_message=ABSTENTION, history=history, include_few_shot=False,
    )

    contents = [m.content for m in messages]
    assert "Why is my webhook failing?" in contents
    # Exactly one SOURCES block — the current one, in the final message.
    assert sum(1 for c in contents if "SOURCES:" in c) == 1
    assert "SOURCES:" in messages[-1].content


# --------------------------------------------------------- rewrite prompt --


def test_rewrite_prompt_renders_history_as_data_not_as_turns():
    """We want the model analysing the conversation, not participating in it.
    Replaying it as real turns reliably produces an answer instead of a
    rewrite."""
    history = [
        Turn(role="user", content="Why is my webhook failing?"),
        Turn(role="assistant", content="It retries 3 times."),
    ]
    messages = build_rewrite_messages("what about backoff?", history)

    assert [m.role for m in messages] == ["system", "user"]
    assert "User: Why is my webhook failing?" in messages[1].content
    assert "Assistant: It retries 3 times." in messages[1].content


def test_rewrite_prompt_protects_identifiers():
    """"Never correct or expand an identifier" is in the prompt because a
    rewriter that helpfully turns ERR_TIMEOUT_502 into "timeout error" destroys
    the exact-match signal the BM25 leg exists for."""
    messages = build_rewrite_messages("q", [Turn(role="user", content="x")])
    assert "ERR_TIMEOUT_502" in messages[0].content
