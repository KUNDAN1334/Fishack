"""Writing trace rows (Design.md §12).

    "Every request traced: tokens, cost, latency per stage (retrieval /
     rerank / generation), cache hit/miss."

Three decisions worth stating.

WRITTEN AFTER THE RESPONSE, NEVER BEFORE. The trace is a record of what
happened, so it lands once, complete, at the end. The alternative — insert a
row at the start and UPDATE it as stages finish — doubles the write path,
leaves half-written rows behind whenever anything throws, and makes every
aggregate query in /stats need a "WHERE complete = true" it can silently
forget. The cost of writing last is that a request which crashes mid-flight
leaves no trace; that is what logs are for.

TRACING NEVER FAILS A REQUEST. Every write is wrapped. A user who got a good
answer must not receive a 500 because an observability INSERT hit a
constraint. This is the same rule as `LLMClient._record_budget`, and it is
worth being consistent about: instrumentation that can break the thing it
instruments is worse than no instrumentation, because it fails exactly when
the system is already under stress.

CHUNK IDS, NOT CHUNK TEXT. `retrieved_chunk_ids` is a UUID[] pointing into
`chunks`. Phase 4's recall metrics compare against those ids, Phase 5's triage
joins on them, and the text is always recoverable. Denormalizing the text
would make the traces table larger than the corpus within a week.
"""

from __future__ import annotations

import json
import logging
import uuid

import asyncpg

from app.generation.models import ChatResponse

logger = logging.getLogger(__name__)


async def record_trace(pool: asyncpg.Pool, response: ChatResponse) -> str | None:
    """Persist one request. Returns the trace id, or None if the write failed.

    Never raises — see the module docstring.
    """
    try:
        chunk_ids = [
            uuid.UUID(citation.chunk_id) for citation in response.citations
        ]
    except (ValueError, AttributeError):
        # Non-UUID chunk ids only happen in tests with synthetic data. Better
        # to trace without the ids than to lose the row entirely.
        chunk_ids = []

    citation_report = (
        response.citation_report.model_dump(mode="json")
        if response.citation_report is not None
        else None
    )
    if citation_report is not None:
        # Derived numbers stored alongside the detail so /stats can aggregate
        # them without re-deriving the logic in SQL — two implementations of
        # "grounded" would eventually disagree.
        citation_report["grounding_rate"] = response.citation_report.grounding_rate
        citation_report["has_fabricated_citations"] = (
            response.citation_report.has_fabricated_citations
        )

    try:
        async with pool.acquire() as conn:
            trace_id = await conn.fetchval(
                """
                INSERT INTO traces (
                    tenant_id, conversation_id, query, rewritten_query, action,
                    answer, confidence, retrieved_chunk_ids, citation_report,
                    provider, model, failover_events, tokens_in, tokens_out,
                    virtual_cost_usd, cache_status, retrieval_ms, rerank_ms,
                    generation_ms, total_ms
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8::uuid[], $9::jsonb,
                    $10, $11, $12::jsonb, $13, $14,
                    $15, $16, $17, $18,
                    $19, $20
                )
                RETURNING id
                """,
                response.tenant_id,
                _as_uuid(response.conversation_id),
                response.rewrite.original if response.rewrite else "",
                # NULL when rewriting did not change anything — so a query
                # like "how many turns actually got rewritten?" is a simple
                # NOT NULL count rather than a string comparison.
                (
                    response.rewrite.rewritten
                    if response.rewrite and response.rewrite.changed
                    else None
                ),
                response.action,
                response.answer,
                response.confidence,
                chunk_ids,
                json.dumps(citation_report) if citation_report is not None else None,
                response.provider,
                response.model,
                json.dumps(response.failover_events),
                response.tokens_in,
                response.tokens_out,
                response.virtual_cost_usd,
                # Phase 5 owns caching; until then every request is a miss,
                # recorded explicitly so the column is never NULL-ambiguous.
                "miss",
                response.retrieval_ms,
                response.rerank_ms,
                response.generation_ms,
                response.total_ms,
            )
        return str(trace_id)
    except Exception:  # noqa: BLE001 — observability must not break the request
        logger.exception("failed to record trace for tenant %s", response.tenant_id)
        return None


async def link_escalation_to_trace(
    pool: asyncpg.Pool, escalation_id: str, trace_id: str
) -> None:
    """Backfill `escalations.trace_id`.

    Ordering problem: the escalation must exist before we answer (the user is
    told we are escalating), but the trace cannot be written until the request
    is complete. So the link is set afterwards. Also best-effort — a missing
    link costs a join in triage, not correctness.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE escalations SET trace_id = $1 WHERE id = $2",
                uuid.UUID(trace_id), uuid.UUID(escalation_id),
            )
    except Exception:  # noqa: BLE001
        logger.exception("failed to link escalation %s to trace %s", escalation_id, trace_id)


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """Client-supplied conversation ids are untrusted input. A malformed one
    must not cost us the trace row."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        logger.warning("ignoring malformed conversation_id %r", value)
        return None
