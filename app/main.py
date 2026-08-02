"""FastAPI application entrypoint.

Phase 0: startup wiring (Postgres pool, Redis, LLM client) + /health.
Phase 3: the embedding/reranker models, the retrieval and chat pipelines, and
         POST /chat. The feedback and admin routers arrive in Phase 5.

Wiring pattern: long-lived resources are created once in the lifespan context
and stored on app.state — request handlers pull them from there. No globals,
so tests can build an app against fakes.

Model loading happens at STARTUP, not on first request. bge-small plus
bge-reranker-base take several seconds and ~450MB; paying that during boot
means the first user gets a normal response instead of a ten-second one, and
it means a missing model fails the deploy rather than the first customer.
"""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

from app.api.routes_chat import router as chat_router
from app.config import get_settings
from app.db.engine import check_database, create_pool
from app.embeddings.encoder import get_encoder
from app.embeddings.service import EmbeddingService
from app.generation.citations import CitationValidator
from app.generation.generator import Generator
from app.generation.pipeline import ChatPipeline
from app.generation.rewriter import QueryRewriter
from app.llm.budget import BudgetTracker
from app.llm.client import build_llm_client
from app.retrieval.service import build_retrieval_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.db_pool = await create_pool(settings.database_url)
    app.state.redis = aioredis.from_url(settings.redis_url)
    app.state.budget = BudgetTracker(app.state.redis)
    app.state.llm = build_llm_client(settings, budget=app.state.budget)

    logger.info("loading local models (embedding + reranker)...")
    encoder = get_encoder(settings.embedding_model_name)
    if encoder.dimension != settings.embedding_dim:
        # Fail the boot, loudly. A dimension mismatch against the vector(384)
        # column would otherwise surface as a per-query error under load
        # (ADR-005).
        raise RuntimeError(
            f"embedding model {settings.embedding_model_name} produces "
            f"{encoder.dimension} dims, schema expects {settings.embedding_dim}"
        )
    app.state.embeddings = EmbeddingService(app.state.db_pool, encoder)
    app.state.retrieval = build_retrieval_service(app.state.embeddings, settings)

    app.state.chat_pipeline = ChatPipeline(
        pool=app.state.db_pool,
        retrieval=app.state.retrieval,
        rewriter=QueryRewriter(
            app.state.llm,
            enabled=settings.query_rewrite_enabled,
            history_turns=settings.query_rewrite_history_turns,
            max_tokens=settings.query_rewrite_max_tokens,
        ),
        generator=Generator(
            app.state.llm,
            abstention_message=settings.abstention_message,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        ),
        validator=CitationValidator(
            app.state.embeddings,
            similarity_threshold=settings.citation_similarity_threshold,
            enabled=settings.citation_validation_enabled,
        ),
        embeddings=app.state.embeddings,
        settings=settings,
    )

    logger.info(
        "Fishly up. LLM chain: %s", " -> ".join(p.name for p in app.state.llm.providers)
    )
    yield
    await app.state.db_pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="Fishly", version="0.3.0", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health(request: Request) -> dict:
    """Liveness + dependency check. Each dependency reports independently so
    a broken Redis doesn't mask a healthy Postgres (or vice versa)."""
    result: dict = {"status": "ok"}

    try:
        result["database"] = await check_database(request.app.state.db_pool)
    except Exception as exc:  # noqa: BLE001 — health endpoints report, not raise
        result["database"] = {"error": str(exc)}
        result["status"] = "degraded"

    try:
        await request.app.state.redis.ping()
        result["redis"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        result["redis"] = {"error": str(exc)}
        result["status"] = "degraded"

    result["llm_chain"] = [p.name for p in request.app.state.llm.providers]
    return result
