"""Feedback triage (Design.md §10).

Pure functions over a trace dict, so every classification path is testable
without a database. The point of these tests is not that the categories are
"right" in some absolute sense — it is that the ORDER of checks is right.

Order is the whole design. Blaming the prompt for chunks that never arrived
sends someone to rewrite a prompt for a retrieval bug, and the real problem
survives the investigation.
"""

import pytest

from app.feedback.triage import (
    CACHE_FAILURE,
    GENERATION_FAILURE,
    RETRIEVAL_FAILURE,
    STALE_DATA,
    UNCLEAR,
    classify,
    summarize,
)


def trace(**kwargs) -> dict:
    defaults = dict(
        id="t1", query="how many retries?", action="answered", confidence=0.8,
        cache_status="miss", citation_report={"grounding_rate": 1.0},
        retrieved_chunk_ids=["c1", "c2"], contested_cited=False,
    )
    defaults.update(kwargs)
    return defaults


# -------------------------------------------------------- cache first --


def test_a_semantic_hit_is_blamed_on_the_cache_not_retrieval():
    """Checked FIRST because a cache hit means retrieval and generation never
    ran for this request. Blaming retrieval for an answer it did not produce
    sends you to debug the wrong component entirely."""
    result = classify(trace(cache_status="semantic_hit", confidence=0.0,
                            retrieved_chunk_ids=[]))
    assert result.category == CACHE_FAILURE
    assert "similar" in result.reason


def test_an_exact_hit_is_also_a_cache_failure():
    """Either it was wrong when cached, or the source changed and invalidation
    missed it. Both are cache problems, not model problems."""
    assert classify(trace(cache_status="exact_hit")).category == CACHE_FAILURE


def test_cache_outranks_even_a_missing_retrieval():
    """A cache hit has no retrieval by definition — empty chunk ids must not
    be read as a retrieval failure."""
    result = classify(trace(cache_status="exact_hit", retrieved_chunk_ids=[]))
    assert result.category == CACHE_FAILURE


# --------------------------------------------------- stale data second --


def test_citing_a_contested_chunk_is_a_stale_data_failure():
    """The model may have followed the prompt perfectly while the CONTEXT was
    out of date. That is an ingestion problem wearing a generation problem's
    clothes — which is why it is checked before generation."""
    result = classify(trace(contested_cited=True))
    assert result.category == STALE_DATA
    assert "conflict rule" in result.reason


def test_stale_data_outranks_a_healthy_looking_generation():
    result = classify(trace(contested_cited=True,
                            citation_report={"grounding_rate": 1.0}))
    assert result.category == STALE_DATA


# ---------------------------------------------------- retrieval third --


def test_no_chunks_at_all_is_a_retrieval_failure():
    assert classify(trace(retrieved_chunk_ids=[])).category == RETRIEVAL_FAILURE


def test_abstaining_with_a_low_score_is_a_retrieval_failure():
    """The user asked something answerable and we refused. The gate did its
    job; retrieval did not give it anything to work with."""
    result = classify(trace(action="escalated", confidence=0.31))
    assert result.category == RETRIEVAL_FAILURE
    assert "0.31" in result.reason


def test_retrieval_is_checked_before_generation():
    """If the right chunks never arrived, no prompt could have produced a good
    answer — so generation cannot be at fault, however bad the grounding
    looks."""
    result = classify(trace(retrieved_chunk_ids=[],
                            citation_report={"grounding_rate": 0.0}))
    assert result.category == RETRIEVAL_FAILURE


# --------------------------------------------------- generation fourth --


def test_fabricated_citations_are_a_generation_failure():
    result = classify(trace(citation_report={
        "has_fabricated_citations": True, "invalid_indices": [9],
    }))
    assert result.category == GENERATION_FAILURE
    assert result.signals["invalid_indices"] == [9]


def test_poor_grounding_is_a_generation_failure():
    result = classify(trace(citation_report={"grounding_rate": 0.4}))
    assert result.category == GENERATION_FAILURE
    assert "40%" in result.reason


def test_a_healthy_looking_but_disliked_answer_is_still_generation():
    """Everything measurable looks fine and the user disliked it anyway. The
    answer was probably unhelpful rather than unsupported — a real category,
    and the reason says to go read it."""
    result = classify(trace())
    assert result.category == GENERATION_FAILURE
    assert "read it" in result.reason


# -------------------------------------------------------------- unclear --


def test_ambiguous_traces_are_not_forced_into_a_bucket():
    """A misclassified failure is worse than an unclassified one: it sends
    someone to fix the wrong component while the real bug survives."""
    result = classify(trace(action="escalated", confidence=0.0,
                            retrieved_chunk_ids=["c1"], citation_report={}))
    assert result.category == UNCLEAR


# -------------------------------------------------- reporting helpers --


def test_every_category_names_a_component_to_fix():
    """A triage report that says 'retrieval' without saying what to do with
    that is a label, not a diagnosis."""
    for case in [
        trace(retrieved_chunk_ids=[]),
        trace(contested_cited=True),
        trace(cache_status="exact_hit"),
        trace(citation_report={"grounding_rate": 0.2}),
    ]:
        assert classify(case).suggested_fix


def test_summarize_orders_by_size():
    """Biggest bucket first — that is the number that decides what to work on
    next."""
    triaged = [
        classify(trace(retrieved_chunk_ids=[])),
        classify(trace(retrieved_chunk_ids=[])),
        classify(trace(contested_cited=True)),
    ]
    counts = summarize(triaged)
    assert list(counts)[0] == RETRIEVAL_FAILURE
    assert counts[RETRIEVAL_FAILURE] == 2


def test_classification_preserves_the_query_for_the_report():
    result = classify(trace(query="why is my webhook failing?"))
    assert result.query == "why is my webhook failing?"
    assert result.trace_id == "t1"
