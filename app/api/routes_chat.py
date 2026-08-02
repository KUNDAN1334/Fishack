"""POST /chat — the streaming answer endpoint (Design.md §2).

Streaming format is SSE, hand-rolled the same way the LLM providers' SSE is
parsed by hand in `app/llm/providers/openai_compat.py`. It is six lines of
framing and it keeps the wire format something you can read in a terminal with
curl, which matters a lot when debugging the Phase 6 frontend.

Event types match `StreamChunk`: `meta` (citations, before any text), `delta`
(answer fragments), `final` (the complete response with the citation report),
`error`. Each is emitted as a named SSE event so the browser's EventSource can
dispatch on it without parsing the payload first.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.generation.models import ChatRequest, StreamChunk

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def sse(chunk: StreamChunk) -> str:
    """Frame one event.

    `ensure_ascii=False` keeps the payload compact and readable; the blank
    line terminator is what actually flushes an event to the client, and
    forgetting it produces a stream that appears to hang.
    """
    payload = chunk.model_dump(mode="json", exclude_none=True)
    return f"event: {chunk.type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _known_tenant(request: Request, tenant_id: str) -> bool:
    async with request.app.state.db_pool.acquire() as conn:
        return await conn.fetchval("SELECT true FROM tenants WHERE id = $1", tenant_id) or False


@router.post("/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """Answer a question, streaming.

    Tenant handling: the id arrives in the body because Phase 6's tenant
    switcher is a UI control, not an auth boundary — this is a demo system
    with no login. It is validated against the `tenants` table so a typo
    produces a 404 rather than an empty result set that looks like "we have no
    documentation about that".

    PRODUCTION NOTE: in a real deployment tenant_id comes from the
    authenticated session or a JWT claim and is NEVER accepted from the
    request body — a client-supplied tenant id is a trivial cross-tenant read.
    `TenantScope` would be constructed from the auth context instead. The
    pipeline below does not change; only where the string comes from does.
    """
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    if not await _known_tenant(request, body.tenant_id):
        raise HTTPException(status_code=404, detail=f"unknown tenant {body.tenant_id!r}")

    pipeline = request.app.state.chat_pipeline

    async def event_stream():
        try:
            async for chunk in pipeline.stream(body):
                yield sse(chunk)
        except Exception as exc:  # noqa: BLE001 — the response has already begun
            # Headers are long gone, so a 500 is not available to us. Emit a
            # terminal error event instead: the client gets a definite end
            # state rather than a connection that just stops, which is
            # indistinguishable from a network failure.
            logger.exception("chat stream failed for tenant %s", body.tenant_id)
            yield sse(StreamChunk(type="error", text=f"{type(exc).__name__}: {exc}"))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells nginx and friends not to buffer, which would defeat
            # streaming entirely and is a genuinely confusing thing to debug:
            # it works locally and "hangs" behind a proxy.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/sync")
async def chat_sync(request: Request, body: ChatRequest) -> dict:
    """Non-streaming variant.

    Exists because streaming is miserable to test with a plain HTTP client and
    because the Phase 4 eval harness wants a single JSON object. It runs the
    identical pipeline — `answer()` just drains `stream()` — so it can never
    diverge from what users actually get.
    """
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")
    if not await _known_tenant(request, body.tenant_id):
        raise HTTPException(status_code=404, detail=f"unknown tenant {body.tenant_id!r}")

    response = await request.app.state.chat_pipeline.answer(body)
    return response.model_dump(mode="json")
