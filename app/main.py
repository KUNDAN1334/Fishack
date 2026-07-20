"""FastAPI application entrypoint.

Phase 0 scope: startup wiring (Postgres pool, Redis, LLM client) + /health.
The chat/feedback/admin routers arrive in Phases 3/5.

Wiring pattern: long-lived resources are created once in the lifespan
context and stored on app.state — request handlers pull them from there.
No globals, so tests can build an app against fakes.
"""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

from app.config import get_settings
from app.db.engine import check_database, create_pool
from app.llm.budget import BudgetTracker
from app.llm.client import build_llm_client

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
    logger.info(
        "Fishly up. LLM chain: %s", " -> ".join(p.name for p in app.state.llm.providers)
    )
    yield
    await app.state.db_pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="Fishly", version="0.1.0", lifespan=lifespan)


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
