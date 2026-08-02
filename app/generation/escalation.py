"""The abstain path's durable record (Design.md §2 branch A).

    "Branch A (Low confidence) -> 'I don't have enough information' + escalate
     to human agent + ticket auto-create with context."

The design point worth defending: an escalation is only useful if the human
picking it up does not have to start over. So the row carries the full context
the bot had at the moment it gave up — the question, the conversation, and the
chunks it retrieved with their scores. A ticket that says only "the bot could
not answer this" makes the human redo the search that already failed.

The secondary use is the one that compounds. Design.md §10 turns escalations
into the data flywheel: Phase 5's triage script classifies each one as a
retrieval failure (the right chunks were never found), a generation failure
(they were found and the answer was still wrong), or a stale-data failure —
and that classification is only possible because the retrieved chunks and
their scores were saved. Storing just the query would make every escalation
unclassifiable after the fact.

Which is why every abstention writes a row, including out-of-scope questions
where retrieval found nothing. Those are not noise: a cluster of them is the
single clearest signal of what customers ask about that you have not
documented, and it is invisible if you only record the near-misses.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from app.generation.models import GateDecision, Turn
from app.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)

REASON_LOW_CONFIDENCE = "low_confidence"
REASON_NO_RESULTS = "no_results"
REASON_MODEL_ABSTAINED = "model_abstained"
REASON_GENERATION_FAILED = "generation_failed"


def _context_payload(retrieval: RetrievalResult | None, gate: GateDecision | None) -> dict:
    """What the bot knew when it gave up.

    Chunk TEXT is deliberately truncated to 400 characters per chunk. The full
    text is recoverable from `chunk_id`, and storing it inline would balloon
    the escalations table with a second copy of the corpus — while a human
    triaging needs only enough to judge "was this the right chunk?".
    """
    payload: dict = {}
    if gate is not None:
        payload["gate"] = {
            "reason": gate.reason,
            "top_score": gate.top_score,
            "threshold": gate.threshold,
            "score_kind": gate.score_kind,
        }
    if retrieval is not None:
        payload["mode"] = retrieval.mode
        payload["degraded_legs"] = retrieval.degraded_legs
        payload["retrieved"] = [
            {
                "chunk_id": scored.chunk.chunk_id,
                "title": scored.chunk.title,
                "heading_path": scored.chunk.heading_path,
                "source_type": scored.chunk.source_type,
                "doc_version": scored.chunk.doc_version,
                "fused_score": round(scored.fused_score, 6),
                "rerank_score": (
                    round(scored.rerank_score, 4) if scored.rerank_score is not None else None
                ),
                "found_by_both_legs": scored.found_by_both_legs,
                "excerpt": scored.chunk.content[:400],
            }
            # Top 10, not top 5: triage needs to see the near-misses that did
            # NOT make the cut, because "the right chunk was at rank 7" and
            # "the right chunk was never retrieved" are different bugs with
            # different fixes.
            for scored in retrieval.candidates[:10]
        ]
    return payload


async def create_escalation(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    query: str,
    reason: str,
    trace_id: str | None = None,
    history: list[Turn] | None = None,
    retrieval: RetrievalResult | None = None,
    gate: GateDecision | None = None,
) -> str | None:
    """Write the escalation row. Returns its id, or None if the write failed.

    Never raises. The user has already been told we are escalating; failing
    the whole request because a bookkeeping INSERT did not land would turn a
    graceful degradation into an outage. The failure is logged loudly instead
    — and it is the kind of thing /stats should surface, since silently
    losing escalations would hollow out the feedback loop.
    """
    try:
        async with pool.acquire() as conn:
            escalation_id = await conn.fetchval(
                """
                INSERT INTO escalations (
                    tenant_id, trace_id, query, chat_history, context, reason, status
                )
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, 'open')
                RETURNING id
                """,
                tenant_id,
                trace_id,
                query,
                json.dumps([turn.model_dump() for turn in (history or [])]),
                json.dumps(_context_payload(retrieval, gate), default=str),
                reason,
            )
        logger.info(
            "escalation %s created for tenant %s (reason=%s)", escalation_id, tenant_id, reason
        )
        return str(escalation_id)
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("failed to record escalation for tenant %s", tenant_id)
        return None
