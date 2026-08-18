"""The chat pipeline end to end, with everything external stubbed.

The assertions that matter here are the HARD ones Design.md demands and Phase 4
will re-check against the golden set:

  * a low-confidence query MUST abstain, and MUST NOT call the LLM
  * an out-of-scope query (nothing retrieved) MUST abstain
  * every abstention MUST produce an escalation row
  * every request MUST produce a trace row, whatever happened
  * the model abstaining MUST be recorded as an escalation, not an answer

No database, no models, no network — so these run on every push, which is the
only way a hard assertion stays hard.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.config import Settings
from app.generation import escalation as escalation_module
from app.generation import pipeline as pipeline_module
from app.generation.citations import CitationValidator
from app.generation.generator import Generator
from app.generation.models import ChatRequest, Turn
from app.generation.pipeline import ChatPipeline
from app.generation.rewriter import QueryRewriter
from app.llm.base import LLMResponse, StreamEvent, TokenUsage
from app.retrieval.models import RetrievalResult, RetrievedChunk, ScoredChunk
from app.retrieval.service import AllLegsFailedError

ABSTENTION = (
    "I don't have enough information to answer this confidently. "
    "I'm escalating this to a human agent."
)


# ------------------------------------------------------------------ stubs --


class StubRetrieval:
    def __init__(self, results=None, error=None):
        self.results = results if results is not None else []
        self.error = error
        self.calls = 0
        self.last_query = None

    async def retrieve(self, scope, query, *, mode="hybrid", top_k=None):
        self.calls += 1
        self.last_query = query
        if self.error:
            raise self.error
        return RetrievalResult(
            query=query, tenant_id=scope.tenant_id, mode=mode,
            results=self.results, candidates=self.results,
            retrieval_ms=5, rerank_ms=10,
        )


class StubLLM:
    """Serves the rewriter (complete) and the generator (stream)."""

    def __init__(self, answer: str = "Retries cap at five attempts [1].", rewrite: str = ""):
        self.answer = answer
        self.rewrite = rewrite
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, messages, *, temperature=None, max_tokens=None):
        self.complete_calls += 1
        return LLMResponse(
            text=self.rewrite, provider="stub", model="stub-1", usage=TokenUsage()
        )

    async def stream(self, messages, *, temperature=None, max_tokens=None):
        self.stream_calls += 1
        for word in self.answer.split():
            yield StreamEvent(type="delta", text=word + " ")
        yield StreamEvent(
            type="done",
            response=LLMResponse(
                text=self.answer, provider="stub", model="stub-1",
                usage=TokenUsage(input_tokens=100, output_tokens=20),
                virtual_cost_usd=0.0001,
            ),
        )


class ExplodingLLM(StubLLM):
    async def stream(self, messages, *, temperature=None, max_tokens=None):
        self.stream_calls += 1
        raise RuntimeError("all providers failed")
        yield  # pragma: no cover — makes this an async generator


class StubEmbeddings:
    async def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        return [1.0, 0.0]


class FakePool:
    """asyncpg.Pool stand-in. The pipeline only ever acquires a connection to
    write escalations and traces, both of which are recorded here."""

    def __init__(self):
        self.escalations: list[dict] = []
        self.traces: list[dict] = []

    def acquire(self):
        raise AssertionError("pipeline tests stub the writers, not the pool")


def scored(chunk_id="c1", *, rerank=0.8, fused=0.03, content="Retries cap at 5.") -> ScoredChunk:
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=chunk_id, document_id=f"d-{chunk_id}", tenant_id="acme",
            content=content, heading_path="Webhooks > Retry Logic",
            title="Webhooks Overview", source_type="docs", source_path="w.md",
            doc_version="v2.2", effective_date=dt.date(2026, 3, 12),
        ),
        fused_score=fused, rerank_score=rerank, fused_rank=1,
    )


@pytest.fixture
def recorded(monkeypatch):
    """Capture escalation and trace writes instead of hitting Postgres."""
    captured = {"escalations": [], "traces": [], "links": []}

    async def fake_escalation(pool, **kwargs):
        captured["escalations"].append(kwargs)
        return f"esc-{len(captured['escalations'])}"

    async def fake_trace(pool, response):
        captured["traces"].append(response)
        return f"trace-{len(captured['traces'])}"

    async def fake_link(pool, escalation_id, trace_id):
        captured["links"].append((escalation_id, trace_id))

    monkeypatch.setattr(escalation_module, "create_escalation", fake_escalation)
    monkeypatch.setattr(pipeline_module.escalation_module, "create_escalation", fake_escalation)
    monkeypatch.setattr(pipeline_module, "record_trace", fake_trace)
    monkeypatch.setattr(pipeline_module, "link_escalation_to_trace", fake_link)
    return captured


def build_pipeline(*, retrieval, llm, settings=None) -> ChatPipeline:
    settings = settings or Settings(
        abstention_message=ABSTENTION,
        confidence_threshold_rerank=0.45,
        confidence_threshold_fused=0.015,
    )
    embeddings = StubEmbeddings()
    return ChatPipeline(
        pool=FakePool(),
        retrieval=retrieval,
        rewriter=QueryRewriter(llm),
        generator=Generator(llm, abstention_message=settings.abstention_message),
        validator=CitationValidator(
            embeddings, similarity_threshold=0.5, abstention_message=ABSTENTION
        ),
        embeddings=embeddings,
        settings=settings,
    )


async def collect(pipeline, request):
    events = []
    async for event in pipeline.stream(request):
        events.append(event)
    return events


# ------------------------------------------------------- the happy path --


async def test_confident_query_is_answered_with_citations(recorded):
    retrieval = StubRetrieval([scored()])
    llm = StubLLM("Retries cap at five attempts per delivery [1].")
    pipeline = build_pipeline(retrieval=retrieval, llm=llm)

    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="retry limit?"))

    assert response.action == "answered"
    assert "[1]" in response.answer
    assert len(response.citations) == 1
    assert response.citation_report is not None
    assert recorded["escalations"] == []
    assert len(recorded["traces"]) == 1


async def test_event_order_is_meta_then_deltas_then_final(recorded):
    """A contract with the frontend: sources render while the answer types."""
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())
    events = await collect(pipeline, ChatRequest(tenant_id="acme", query="q"))

    assert events[0].type == "meta"
    assert events[-1].type == "final"
    assert all(e.type == "delta" for e in events[1:-1])
    assert events[0].data["citations"], "citations must arrive before any text"


async def test_per_stage_timings_are_recorded(recorded):
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())
    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert response.retrieval_ms == 5
    assert response.rerank_ms == 10
    assert response.generation_ms >= 0
    assert response.total_ms >= 0
    assert response.tokens_in == 100 and response.tokens_out == 20


# ------------------------------------------------ HARD: must abstain --


async def test_low_confidence_abstains_without_calling_the_llm(recorded):
    """Design.md §7 technique 5. The gate's whole value is that it costs zero
    tokens — if the LLM is called anyway, the control is decorative."""
    retrieval = StubRetrieval([scored(rerank=0.1)])
    llm = StubLLM()
    pipeline = build_pipeline(retrieval=retrieval, llm=llm)

    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="unrelated"))

    assert response.action == "escalated"
    assert response.answer == ABSTENTION
    assert llm.stream_calls == 0, "the gate must abstain BEFORE generation"
    assert response.gate.should_generate is False


async def test_out_of_scope_query_abstains(recorded):
    """Nothing retrieved. top_score is 0.0, so no threshold can admit it."""
    pipeline = build_pipeline(retrieval=StubRetrieval([]), llm=StubLLM())
    response = await pipeline.answer(
        ChatRequest(tenant_id="acme", query="what is the capital of France?")
    )

    assert response.action == "escalated"
    assert response.gate.reason == "no_results"
    assert response.citations == []


async def test_abstention_still_streams_like_a_normal_answer(recorded):
    """A separate shape for abstentions would force every consumer to branch
    on something that is a legitimate outcome, not a failure."""
    pipeline = build_pipeline(retrieval=StubRetrieval([]), llm=StubLLM())
    events = await collect(pipeline, ChatRequest(tenant_id="acme", query="q"))

    assert [e.type for e in events] == ["meta", "delta", "final"]
    assert events[1].text == ABSTENTION


# --------------------------------------- HARD: escalation + trace always --


@pytest.mark.parametrize(
    "retrieval,expected_reason",
    [
        (StubRetrieval([]), escalation_module.REASON_NO_RESULTS),
        (StubRetrieval([scored(rerank=0.1)]), escalation_module.REASON_LOW_CONFIDENCE),
    ],
)
async def test_every_abstention_creates_an_escalation(recorded, retrieval, expected_reason):
    """Including out-of-scope questions. A cluster of those is the clearest
    signal of what customers ask about that you have not documented — and it
    is invisible if you only record the near-misses."""
    pipeline = build_pipeline(retrieval=retrieval, llm=StubLLM())
    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert len(recorded["escalations"]) == 1
    assert recorded["escalations"][0]["reason"] == expected_reason
    assert response.escalation_id is not None


async def test_escalation_carries_the_context_a_human_needs(recorded):
    """A ticket saying only "the bot could not answer" makes the human redo
    the search that already failed."""
    history = [Turn(role="user", content="earlier question")]
    pipeline = build_pipeline(retrieval=StubRetrieval([scored(rerank=0.1)]), llm=StubLLM())
    await pipeline.answer(
        ChatRequest(tenant_id="acme", query="q", messages=history)
    )

    recorded_escalation = recorded["escalations"][0]
    assert recorded_escalation["history"] == history
    assert recorded_escalation["retrieval"] is not None
    assert recorded_escalation["gate"] is not None


@pytest.mark.parametrize(
    "retrieval,llm",
    [
        (StubRetrieval([scored()]), StubLLM()),                       # answered
        (StubRetrieval([]), StubLLM()),                               # abstained
        (StubRetrieval([scored()]), ExplodingLLM()),                  # failed
        (StubRetrieval(error=AllLegsFailedError("db down")), StubLLM()),  # retrieval died
    ],
)
async def test_every_outcome_produces_exactly_one_trace(recorded, retrieval, llm):
    """Observability is not optional on the unhappy paths — those are the ones
    you need it for. One row, never zero, never two."""
    pipeline = build_pipeline(retrieval=retrieval, llm=llm)
    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert len(recorded["traces"]) == 1
    assert response.trace_id is not None


async def test_escalations_are_linked_to_their_trace(recorded):
    pipeline = build_pipeline(retrieval=StubRetrieval([]), llm=StubLLM())
    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    assert recorded["links"] == [("esc-1", "trace-1")]


# ------------------------------------------- the model's own abstention --


async def test_model_abstention_is_recorded_as_an_escalation(recorded):
    """The gate passed but the model read the context and declined — the case
    scores cannot catch, because the chunks were topically right and factually
    silent. Counted so the escalation-rate metric reflects reality."""
    llm = StubLLM(answer=ABSTENTION)
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=llm)

    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert llm.stream_calls == 1, "the gate should have passed"
    assert response.action == "escalated"
    assert recorded["escalations"][0]["reason"] == escalation_module.REASON_MODEL_ABSTAINED
    # No citation report: there are no claims to validate.
    assert response.citation_report is None


# ----------------------------------------------------- failure handling --


async def test_generation_failure_escalates_rather_than_erroring(recorded):
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=ExplodingLLM())
    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert response.action == "escalated"
    assert recorded["escalations"][0]["reason"] == escalation_module.REASON_GENERATION_FAILED


async def test_total_retrieval_failure_escalates(recorded):
    """The database being unreachable is an outage, not "no results" — but the
    user-facing behavior is identical, because we still cannot ground an
    answer."""
    pipeline = build_pipeline(
        retrieval=StubRetrieval(error=AllLegsFailedError("db down")), llm=StubLLM()
    )
    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert response.action == "escalated"
    assert response.answer == ABSTENTION


async def test_fabricated_citations_are_flagged_not_suppressed(recorded):
    """Design.md §7 asks us to flag fake citations in the metadata, not to
    withhold the answer. It may still be correct, and silently swallowing it
    would be its own failure."""
    llm = StubLLM(answer="Retries cap at five attempts per delivery [9].")
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=llm)

    response = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert response.action == "answered"
    assert response.citation_report.has_fabricated_citations is True
    assert response.citation_report.invalid_indices == [9]


# ---------------------------------------------------------- rewriting --


async def test_the_rewritten_query_is_what_gets_retrieved(recorded):
    """The entire point of rewriting. If retrieval used the raw follow-up, the
    step would be an expensive no-op."""
    retrieval = StubRetrieval([scored()])
    llm = StubLLM(rewrite="What is the webhook retry limit after v2.4?")
    pipeline = build_pipeline(retrieval=retrieval, llm=llm)

    await pipeline.answer(
        ChatRequest(
            tenant_id="acme", query="what about it?",
            messages=[Turn(role="user", content="webhooks?")],
        )
    )

    assert retrieval.last_query == "What is the webhook retry limit after v2.4?"


async def test_first_turn_skips_rewriting_entirely(recorded):
    retrieval = StubRetrieval([scored()])
    llm = StubLLM()
    pipeline = build_pipeline(retrieval=retrieval, llm=llm)

    await pipeline.answer(ChatRequest(tenant_id="acme", query="retry limit?"))

    assert llm.complete_calls == 0
    assert retrieval.last_query == "retry limit?"


# ============================================================== caching ==
# Phase 5. The cache changes what the pipeline DOES, so it needs its own hard
# assertions — chiefly that it never caches a refusal and never lets one
# tenant's answer reach another.

import fakeredis.aioredis  # noqa: E402

from app.cache.store import AnswerCache  # noqa: E402


def build_cached_pipeline(*, retrieval, llm, cache=None, settings=None) -> ChatPipeline:
    pipeline = build_pipeline(retrieval=retrieval, llm=llm, settings=settings)
    pipeline.cache = cache or AnswerCache(
        fakeredis.aioredis.FakeRedis(), ttl_seconds=60, semantic_threshold=0.95
    )
    return pipeline


async def test_second_identical_question_is_served_from_cache(recorded):
    """The whole point (Design.md §9): a hit skips retrieval, reranking AND
    generation — the entire expensive part of the request."""
    retrieval = StubRetrieval([scored()])
    llm = StubLLM("Retries cap at five attempts [1].")
    pipeline = build_cached_pipeline(retrieval=retrieval, llm=llm)

    first = await pipeline.answer(ChatRequest(tenant_id="acme", query="retry limit?"))
    second = await pipeline.answer(ChatRequest(tenant_id="acme", query="retry limit?"))

    assert first.cache_status == "miss"
    assert second.cache_status == "exact_hit"
    assert second.action == "cache_hit"
    assert second.answer == first.answer
    assert llm.stream_calls == 1, "a cache hit must not call the model"
    assert retrieval.calls == 1, "a cache hit must not retrieve"


async def test_a_cache_hit_reports_zero_cost_not_the_original(recorded):
    """Replaying the original spend would make /stats describe a request that
    never happened — and inflate cost-per-query exactly when caching is
    working, which is the metric Design.md §9 exists to improve."""
    pipeline = build_cached_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())

    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    second = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert second.tokens_in == 0 and second.tokens_out == 0
    assert second.virtual_cost_usd == 0.0
    # Provider/model describe who wrote it originally — useful for debugging.
    assert second.provider == "stub"


async def test_abstentions_are_never_cached(recorded):
    """HARD ASSERTION. 'I don't have enough information' is a statement about
    the corpus AT ONE MOMENT. Cache it and the refusal survives for an hour
    after someone adds the missing docs — the system would actively decline to
    use content it now has."""
    empty = StubRetrieval([])
    pipeline = build_cached_pipeline(retrieval=empty, llm=StubLLM())

    first = await pipeline.answer(ChatRequest(tenant_id="acme", query="out of scope?"))
    assert first.action == "escalated"

    # Now the corpus gains the answer.
    pipeline.retrieval = StubRetrieval([scored()])
    second = await pipeline.answer(ChatRequest(tenant_id="acme", query="out of scope?"))

    assert second.cache_status == "miss", "a refusal must never be cached"
    assert second.action == "answered"


async def test_the_cache_is_tenant_isolated_through_the_pipeline(recorded):
    """HARD ASSERTION. Phase 2 made cross-tenant reads impossible in SQL;
    serving one from Redis would walk around all of it."""
    shared = fakeredis.aioredis.FakeRedis()
    acme = build_cached_pipeline(
        retrieval=StubRetrieval([scored()]), llm=StubLLM("ACME ONLY ANSWER [1]."),
        cache=AnswerCache(shared, ttl_seconds=60),
    )
    globex_llm = StubLLM("GLOBEX ANSWER [1].")
    globex = build_cached_pipeline(
        retrieval=StubRetrieval([scored()]), llm=globex_llm,
        cache=AnswerCache(shared, ttl_seconds=60),
    )

    await acme.answer(ChatRequest(tenant_id="acme", query="same question"))
    result = await globex.answer(ChatRequest(tenant_id="globex", query="same question"))

    assert result.cache_status == "miss"
    assert "ACME ONLY" not in result.answer
    assert globex_llm.stream_calls == 1, "globex must generate its own answer"


async def test_the_cache_key_uses_the_rewritten_query(recorded):
    """A follow-up ('what about the backoff?') is meaningless as a cache key —
    the same four words mean different things in different conversations. The
    REWRITTEN query is standalone by construction, which is what a key needs
    to be."""
    llm = StubLLM(rewrite="What is the webhook backoff schedule?")
    pipeline = build_cached_pipeline(retrieval=StubRetrieval([scored()]), llm=llm)
    history = [Turn(role="user", content="webhooks?")]

    await pipeline.answer(
        ChatRequest(tenant_id="acme", query="what about the backoff?", messages=history)
    )

    # The standalone form hits; the raw follow-up does not.
    assert await pipeline.cache.get_exact("acme", "What is the webhook backoff schedule?")
    assert await pipeline.cache.get_exact("acme", "what about the backoff?") is None


async def test_cache_status_reaches_the_trace(recorded):
    """/stats computes cache hit rate from this column, so it has to be right
    on both paths."""
    pipeline = build_cached_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())

    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    assert [t.cache_status for t in recorded["traces"]] == ["miss", "exact_hit"]


async def test_a_cache_hit_emits_the_same_event_shape(recorded):
    """The client must not have to branch on whether an answer was cached —
    same meta, delta, final sequence either way."""
    pipeline = build_cached_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())
    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))

    events = await collect(pipeline, ChatRequest(tenant_id="acme", query="q"))
    assert [e.type for e in events] == ["meta", "delta", "final"]
    assert events[0].data["cache_status"] == "exact_hit"


async def test_invalidation_makes_the_next_request_regenerate(recorded):
    """The full Design.md §9 loop: a document changes, ingestion invalidates,
    the next request regenerates instead of serving the stale answer."""
    llm = StubLLM("OLD ANSWER [1].")
    pipeline = build_cached_pipeline(retrieval=StubRetrieval([scored("c1")]), llm=llm)

    await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    assert (await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))).cache_status == "exact_hit"

    await pipeline.cache.invalidate_chunks("acme", ["c1"])

    third = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    assert third.cache_status == "miss"
    assert llm.stream_calls == 2


async def test_a_pipeline_without_a_cache_still_works(recorded):
    """The eval harness runs cacheless on purpose — a cached answer would make
    it score a previous run's output rather than this one's."""
    pipeline = build_pipeline(retrieval=StubRetrieval([scored()]), llm=StubLLM())
    assert pipeline.cache is None
    result = await pipeline.answer(ChatRequest(tenant_id="acme", query="q"))
    assert result.cache_status == "miss" and result.action == "answered"
