"""The chat pipeline — Design.md §2, steps 2 through 12.

    rewrite -> retrieve -> gate -> generate -> validate -> escalate? -> trace

One streaming method, and a non-streaming wrapper built on top of it. There is
deliberately no second implementation for the non-streaming path: two copies of
this orchestration would drift, and the one that drifted would be the eval
harness's, meaning Phase 4 would be measuring a pipeline the product does not
run. `answer()` simply drains `stream()`.

Where the abstention decisions live, because there are three and they are easy
to confuse:

  1. THE GATE (gate.py) — retrieval scored too low. No LLM call at all. This
     is the cheap, reliable one, and Design.md §7.5's whole point.
  2. THE MODEL (generator.is_abstention) — the gate passed, but the model read
     the context and decided it could not answer. Costs a call, catches what
     scores cannot: context that is topically right and factually silent.
  3. GENERATION FAILURE — every provider in the chain failed. Not a judgement,
     an outage; but the user-facing behavior is identical, because "we are
     escalating this to a human" is true either way.

All three produce an escalation row, and all three set action='escalated'.
That last part matters: if only case 1 were counted, the escalation-rate metric
in Design.md §12 would understate reality and look healthy while the system
degraded.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator

import asyncpg

from app.config import Settings
from app.embeddings.service import EmbeddingService
from app.generation import escalation as escalation_module
from app.generation.citations import CitationValidator
from app.generation.gate import evaluate_gate
from app.generation.generator import Generator, is_abstention
from app.generation.models import (
    ChatRequest,
    ChatResponse,
    StreamChunk,
    build_citations,
)
from app.generation.rewriter import QueryRewriter
from app.retrieval.service import AllLegsFailedError, RetrievalService
from app.retrieval.tenant_scope import TenantScope
from app.tracing.recorder import link_escalation_to_trace, record_trace

logger = logging.getLogger(__name__)


class ChatPipeline:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        retrieval: RetrievalService,
        rewriter: QueryRewriter,
        generator: Generator,
        validator: CitationValidator,
        embeddings: EmbeddingService,
        settings: Settings,
    ):
        self.pool = pool
        self.retrieval = retrieval
        self.rewriter = rewriter
        self.generator = generator
        self.validator = validator
        self.embeddings = embeddings
        self.settings = settings

    # ------------------------------------------------------------ public --

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """Non-streaming. Drains stream() so there is exactly one pipeline."""
        final: ChatResponse | None = None
        async for event in self.stream(request):
            if event.type == "final":
                final = ChatResponse.model_validate(event.data)
        assert final is not None, "stream() must always emit a final event"
        return final

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Run the pipeline, yielding SSE events.

        Event order is a contract with the frontend:
          meta   citations + gate decision, BEFORE any text, so the sources
                 panel renders while the answer types
          delta  answer fragments
          final  the complete ChatResponse including the citation report,
                 which cannot exist until the answer does
        """
        started = time.perf_counter()
        response = ChatResponse(
            tenant_id=request.tenant_id, conversation_id=request.conversation_id
        )

        # Tenancy enters here and is carried as a SCOPE, never as a string
        # (ADR-012). Nothing downstream can reach the database without it.
        scope = TenantScope(self.pool, request.tenant_id)

        # -------------------------------------------------- 1. rewrite --
        rewrite = await self.rewriter.rewrite(request.query, request.messages)
        response.rewrite = rewrite
        response.rewrite_ms = rewrite.elapsed_ms
        if rewrite.changed:
            logger.info("rewrote %r -> %r", rewrite.original, rewrite.rewritten)

        # ------------------------------------------------- 2. retrieve --
        try:
            retrieval = await self.retrieval.retrieve(
                scope, rewrite.effective_query, mode="hybrid"
            )
        except AllLegsFailedError as exc:
            # The database is unreachable — not "no results". We cannot ground
            # an answer in nothing, so we escalate rather than let the model
            # improvise (Design.md §7 technique 1: closed-book means no
            # context, no answer).
            logger.exception("retrieval failed entirely")
            async for event in self._abstain(
                request, response, started,
                reason=escalation_module.REASON_NO_RESULTS,
                detail=str(exc),
            ):
                yield event
            return

        response.retrieval = retrieval
        response.retrieval_ms = retrieval.retrieval_ms
        response.rerank_ms = retrieval.rerank_ms
        response.degraded_legs = retrieval.degraded_legs

        # ----------------------------------------------------- 3. gate --
        gate = evaluate_gate(
            retrieval,
            threshold_rerank=self.settings.confidence_threshold_rerank,
            threshold_fused=self.settings.confidence_threshold_fused,
        )
        response.gate = gate
        response.confidence = gate.top_score

        if not gate.should_generate:
            # The cheap abstention: zero tokens spent.
            async for event in self._abstain(
                request, response, started,
                reason=(
                    escalation_module.REASON_NO_RESULTS
                    if gate.reason == "no_results"
                    else escalation_module.REASON_LOW_CONFIDENCE
                ),
            ):
                yield event
            return

        # ------------------------------------------------ 4. generate --
        citations = build_citations(retrieval.results)
        response.citations = citations

        # Sources go out BEFORE the first token. The user sees what the answer
        # will be built from while it is being written, which is a meaningful
        # trust affordance and costs nothing.
        yield StreamChunk(
            type="meta",
            data={
                "citations": [c.model_dump(mode="json") for c in citations],
                "gate": gate.model_dump(mode="json"),
                "rewrite": rewrite.model_dump(mode="json"),
            },
        )

        generation_started = time.perf_counter()
        pieces: list[str] = []
        try:
            async for event in self.generator.stream(
                rewrite.effective_query, citations, retrieval.results, request.messages
            ):
                if event.type == "delta":
                    pieces.append(event.text)
                    yield StreamChunk(type="delta", text=event.text)
                elif event.type == "done" and event.response is not None:
                    response.provider = event.response.provider
                    response.model = event.response.model
                    response.tokens_in = event.response.usage.input_tokens
                    response.tokens_out = event.response.usage.output_tokens
                    response.virtual_cost_usd = event.response.virtual_cost_usd
                    response.failover_events = event.response.failover_events
        except Exception as exc:  # noqa: BLE001 — every provider failed, or died mid-stream
            logger.exception("generation failed")
            partial = "".join(pieces)
            if partial:
                # Deltas already reached the user (LLMClient does not fail over
                # after the first token, ADR/Q3). Do not pretend we abstained —
                # say the generation was interrupted, and still record it.
                yield StreamChunk(type="error", text="generation interrupted")
            async for event in self._abstain(
                request, response, started,
                reason=escalation_module.REASON_GENERATION_FAILED,
                detail=str(exc),
                emit_answer=not partial,
            ):
                yield event
            return

        answer = "".join(pieces).strip()
        response.answer = answer
        response.generation_ms = int((time.perf_counter() - generation_started) * 1000)

        # ------------------------------- 5. did the model itself abstain? --
        if is_abstention(answer, self.settings.abstention_message):
            # The gate passed but the model read the context and declined —
            # the case scores cannot catch, because the chunks were topically
            # right and factually silent. Counted as an escalation so the
            # escalation-rate metric reflects reality.
            response.action = "escalated"
            response.escalation_id = await escalation_module.create_escalation(
                self.pool,
                tenant_id=request.tenant_id,
                query=rewrite.effective_query,
                reason=escalation_module.REASON_MODEL_ABSTAINED,
                history=request.messages,
                retrieval=retrieval,
                gate=gate,
            )
        else:
            # ------------------------------------------- 6. validate --
            chunk_texts = {
                citation.index: scored.chunk.body
                for citation, scored in zip(citations, retrieval.results)
            }
            report, validation_ms = await self.validator.validate(
                answer, citations, chunk_texts
            )
            response.citation_report = report
            response.validation_ms = validation_ms
            response.action = "answered"

            if report.has_fabricated_citations:
                # NOT downgraded to an abstention. The answer may still be
                # correct, and silently withholding it would be its own
                # failure. We surface the flag and let the UI and the feedback
                # loop act on it — Design.md §7 asks us to "flag fake
                # citations in the response metadata", not to suppress.
                logger.warning(
                    "answer cited non-existent sources %s (tenant %s)",
                    report.invalid_indices, request.tenant_id,
                )

        response.total_ms = int((time.perf_counter() - started) * 1000)
        await self._finish(response)
        yield StreamChunk(type="final", data=response.model_dump(mode="json"))

    # --------------------------------------------------------- internals --

    async def _abstain(
        self,
        request: ChatRequest,
        response: ChatResponse,
        started: float,
        *,
        reason: str,
        detail: str | None = None,
        emit_answer: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """The single abstention exit. Every path that gives up comes here.

        Centralized so that the escalation row, the trace action, and the
        user-facing sentence can never disagree — three places that drift
        apart is exactly how an escalation-rate metric ends up lying.
        """
        response.action = "escalated"
        response.answer = self.settings.abstention_message

        response.escalation_id = await escalation_module.create_escalation(
            self.pool,
            tenant_id=request.tenant_id,
            query=(response.rewrite.effective_query if response.rewrite else request.query),
            reason=reason,
            history=request.messages,
            retrieval=response.retrieval,
            gate=response.gate,
        )
        if detail:
            logger.info("abstaining (%s): %s", reason, detail)

        # The abstention still goes out as meta + delta, so the client's
        # rendering path is identical to a normal answer. A separate "error"
        # shape for abstentions would mean every consumer needs two branches
        # for something that is a legitimate outcome, not a failure.
        yield StreamChunk(
            type="meta",
            data={
                "citations": [],
                "gate": response.gate.model_dump(mode="json") if response.gate else None,
                "rewrite": response.rewrite.model_dump(mode="json") if response.rewrite else None,
                "escalated": True,
            },
        )
        if emit_answer:
            yield StreamChunk(type="delta", text=response.answer)

        response.total_ms = int((time.perf_counter() - started) * 1000)
        await self._finish(response)
        yield StreamChunk(type="final", data=response.model_dump(mode="json"))

    async def _finish(self, response: ChatResponse) -> None:
        """Write the trace, then link any escalation to it."""
        trace_id = await record_trace(self.pool, response)
        response.trace_id = trace_id
        if trace_id and response.escalation_id:
            await link_escalation_to_trace(self.pool, response.escalation_id, trace_id)
