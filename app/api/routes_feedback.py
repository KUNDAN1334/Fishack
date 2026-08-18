"""Thumbs up/down (Design.md §10).

    "Har response ke sath 👍/👎 + optional free-text reason logged with
     (query, retrieved_chunks, generated_answer, tenant_id)."

The endpoint is small because the interesting design happened earlier: all of
that context is already on the trace row, so feedback stores a rating and a
`trace_id` rather than duplicating the answer, the chunk ids and the query.

That matters for a reason beyond tidiness. If feedback carried its own copy of
the answer, the two could disagree — and the triage script would be reasoning
about a snapshot rather than what the system actually did. One row of truth,
referenced.

This is where Design.md §10's data flywheel starts: 👎 feeds
`scripts/triage_feedback.py`, which classifies failures as retrieval,
generation or stale-data; 👍 becomes golden-set candidates.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    trace_id: str
    # +1 / -1 rather than a 1-5 scale. Design.md §10 asks for thumbs, and a
    # binary signal is both easier for users to give and easier to act on —
    # "what does a 3 mean?" is not a question the triage script can answer.
    # The CHECK constraint on the column enforces this at the database too.
    rating: int = Field(..., description="1 for thumbs up, -1 for thumbs down")
    comment: str | None = None


@router.post("/feedback")
async def submit_feedback(request: Request, body: FeedbackRequest) -> dict:
    """Record a rating against a trace.

    Tenant comes from the TRACE, never from the request body. The client
    already proved which conversation it is talking about by supplying a
    trace_id; asking it for the tenant as well would create a second, weaker
    source of truth that could disagree with the first — and a way to attach
    feedback to another tenant's trace.
    """
    if body.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating must be 1 or -1")

    try:
        trace_uuid = uuid.UUID(body.trace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="trace_id must be a UUID") from None

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        tenant_id = await conn.fetchval("SELECT tenant_id FROM traces WHERE id = $1", trace_uuid)
        if tenant_id is None:
            # Also covers a trace whose tenant is NULL (internal/eval calls),
            # which should not be rateable.
            raise HTTPException(status_code=404, detail="unknown trace_id")

        feedback_id = await conn.fetchval(
            """
            INSERT INTO feedback (tenant_id, trace_id, rating, comment)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            tenant_id, trace_uuid, body.rating, body.comment,
        )

    logger.info(
        "feedback %s recorded for trace %s (tenant %s, rating %+d)",
        feedback_id, body.trace_id, tenant_id, body.rating,
    )
    return {"feedback_id": str(feedback_id), "trace_id": body.trace_id, "rating": body.rating}
