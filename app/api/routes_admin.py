"""GET /stats — the admin dashboard's data (Design.md §12).

    "A /stats admin endpoint with p50/p95 latency, cost per query, escalation
     rate, cache hit rate."

Everything except provider quota comes from the `traces` table, which has been
written on every request since Phase 3. Two reasons that is the right source
rather than Redis counters:

  * it survives a restart, and "what did last Tuesday look like?" is a
    question you eventually need to answer;
  * the numbers are computed from the same rows the eval harness and the
    triage script read, so three tools cannot disagree about what happened.

Provider quota is the exception — those are genuinely ephemeral daily counters
and already live in Redis (Phase 0's `BudgetTracker`).

PERCENTILES IN SQL. `percentile_cont` is used rather than pulling every row
into Python and sorting. On 10,000 traces the difference is a few hundred
milliseconds versus a few megabytes of transfer, and the aggregate belongs
where the data is.

Access is gated by `require_admin` — see below for why this endpoint, alone in
the codebase, needs it.

PRODUCTION NOTE: at real volume these become a materialized view refreshed on
a schedule, or a rollup table written by a nightly job. Scanning the raw trace
table per dashboard load stops being acceptable somewhere around a million
rows — and the query shape here is deliberately the one you would put behind
such a view.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

logger = logging.getLogger(__name__)


async def require_admin(
    request: Request, x_admin_token: str | None = Header(default=None)
) -> None:
    """Gate the one endpoint that reads across tenants.

    Every other route is tenant-scoped by construction. This one is not — its
    whole job is the cross-tenant view — which makes it the single place where
    "no auth" stops being a demo simplification and becomes a data leak: request
    volume, cost and query counts for every tenant on the system.

    Behaviour:
      * `ADMIN_TOKEN` unset  -> open, and a warning is logged on every call.
        Correct default for local development; the log line is there so it
        cannot be forgotten silently in a deployment.
      * `ADMIN_TOKEN` set    -> `X-Admin-Token` must match, or 401.

    `secrets.compare_digest` rather than `==`: a plain comparison short-circuits
    on the first differing byte, and the timing difference is enough to recover
    a token one character at a time. Cheap to do right.

    PRODUCTION NOTE: a shared bearer token is the floor, not the goal. A real
    deployment puts this behind SSO with an admin role, and audits every access
    — /stats is exactly the endpoint an attacker would use to map your
    customers.
    """
    expected = request.app.state.settings.admin_token
    if not expected:
        logger.warning(
            "/admin accessed with no ADMIN_TOKEN configured — open to anyone who "
            "can reach this port. Set ADMIN_TOKEN before exposing this service."
        )
        return
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="admin token required")


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats")
async def stats(
    request: Request,
    hours: int = Query(default=24, ge=1, le=24 * 90),
    tenant_id: str | None = Query(default=None),
) -> dict:
    """Operational metrics over a time window.

    `tenant_id` is optional here and that is deliberate: this is an ADMIN
    endpoint, whose whole job is the cross-tenant view. It is the one place in
    the system that legitimately reads across tenants.

    Guarded by `require_admin` on the router (see above): open when
    `ADMIN_TOKEN` is unset, token-checked when it is set.
    """
    pool = request.app.state.db_pool
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)

    try:
        async with pool.acquire() as conn:
            overview = await conn.fetchrow(_OVERVIEW_SQL, since, tenant_id)
            by_tenant = await conn.fetch(_BY_TENANT_SQL, since, tenant_id)
            by_action = await conn.fetch(_BY_ACTION_SQL, since, tenant_id)
            feedback = await conn.fetchrow(_FEEDBACK_SQL, since, tenant_id)
            escalations = await conn.fetch(_ESCALATION_SQL, since, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("stats query failed")
        raise HTTPException(status_code=503, detail=f"stats unavailable: {exc}") from exc

    total = overview["requests"] or 0

    return {
        "window": {"hours": hours, "since": since.isoformat(), "tenant_id": tenant_id},
        "requests": {
            "total": total,
            # Design.md §12 lists escalation rate as a headline metric, and
            # notes it cuts both ways: too high means bad retrieval, too low
            # means the confidence gate is not protecting anyone.
            "escalation_rate": _rate(overview["escalated"], total),
            "cache_hit_rate": _rate(overview["cache_hits"], total),
            "by_action": {row["action"] or "unknown": row["n"] for row in by_action},
        },
        "latency_ms": {
            "p50": _int(overview["p50_total"]),
            "p95": _int(overview["p95_total"]),
            # Per-stage means, because "p95 is 4 seconds" is not actionable
            # until you know which stage owns it. On this system the answer is
            # almost always the reranker.
            "mean_retrieval": _int(overview["mean_retrieval"]),
            "mean_rerank": _int(overview["mean_rerank"]),
            "mean_generation": _int(overview["mean_generation"]),
        },
        "cost": {
            # "Virtual" throughout: we run on free tiers, so real spend is $0.
            # This is what the same usage WOULD cost at paid-API prices, using
            # the table in app/config.py. Methodology stated in the payload so
            # nobody reads it as a bill.
            "methodology": "virtual — paid-tier prices applied to free-tier usage",
            "total_usd": _float(overview["total_cost"]),
            "per_query_usd": _float(overview["cost_per_query"]),
            "tokens_in": _int(overview["tokens_in"]),
            "tokens_out": _int(overview["tokens_out"]),
        },
        "quality": {
            "thumbs_up": feedback["up"] or 0,
            "thumbs_down": feedback["down"] or 0,
            "satisfaction_rate": _rate(feedback["up"], (feedback["up"] or 0) + (feedback["down"] or 0)),
            # Cheap proxy for hallucination pressure. Every answer already
            # carries a citation report (Phase 3), so this costs one more
            # aggregate rather than a new pipeline.
            "answers_with_fabricated_citations": overview["fabricated"] or 0,
            "mean_confidence": _float(overview["mean_confidence"]),
        },
        "escalations": {
            "open": sum(r["n"] for r in escalations if r["status"] == "open"),
            "by_reason": {r["reason"]: r["n"] for r in escalations},
        },
        "by_tenant": [
            {
                "tenant_id": row["tenant_id"],
                "requests": row["requests"],
                "escalation_rate": _rate(row["escalated"], row["requests"]),
                "cache_hit_rate": _rate(row["cache_hits"], row["requests"]),
                "cost_usd": _float(row["cost"]),
                "p95_ms": _int(row["p95_total"]),
            }
            for row in by_tenant
        ],
        "providers": await _provider_quota(request),
    }


@router.post("/cache/flush")
async def flush_cache(request: Request, tenant_id: str = Query(...)) -> dict:
    """Drop one tenant's cached answers.

    An operational escape hatch: when something is wrong and you need every
    answer regenerated NOW, waiting an hour for TTL is not an option. Scoped
    to one tenant because a global flush would punish everyone for one
    tenant's problem.
    """
    cache = getattr(request.app.state, "cache", None)
    if cache is None:
        raise HTTPException(status_code=503, detail="cache not configured")
    deleted = await cache.invalidate_tenant(tenant_id)
    logger.info("admin flushed %d cache keys for tenant %s", deleted, tenant_id)
    return {"tenant_id": tenant_id, "keys_deleted": deleted}


# ------------------------------------------------------------ helpers ----


def _rate(part, whole) -> float:
    """Guarded division. A zero-request window must return 0.0, not crash the
    dashboard and not report NaN — which serializes to invalid JSON and breaks
    the frontend rather than the API."""
    if not whole:
        return 0.0
    return round((part or 0) / whole, 4)


def _int(value) -> int:
    return int(value) if value is not None else 0


def _float(value) -> float:
    return round(float(value), 6) if value is not None else 0.0


async def _provider_quota(request: Request) -> dict:
    """Today's per-provider usage from Redis (free-tier requirement #2).

    Best-effort: if Redis is down the rest of /stats is still useful, so this
    degrades to an error field rather than failing the endpoint.
    """
    budget = getattr(request.app.state, "budget", None)
    if budget is None:
        return {}
    try:
        return await budget.snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.warning("provider quota unavailable: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------- SQL ----
# `($2::text IS NULL OR tenant_id = $2)` is the optional-filter idiom: one
# query serves both the global and the per-tenant view, so the two can never
# drift apart in how they compute a rate.

_OVERVIEW_SQL = """
SELECT
    count(*)                                                        AS requests,
    count(*) FILTER (WHERE action = 'escalated')                    AS escalated,
    count(*) FILTER (WHERE cache_status IN ('exact_hit','semantic_hit')) AS cache_hits,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms)           AS p50_total,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms)          AS p95_total,
    avg(retrieval_ms)                                               AS mean_retrieval,
    avg(rerank_ms)                                                  AS mean_rerank,
    avg(generation_ms)                                              AS mean_generation,
    sum(virtual_cost_usd)                                           AS total_cost,
    avg(virtual_cost_usd)                                           AS cost_per_query,
    sum(tokens_in)                                                  AS tokens_in,
    sum(tokens_out)                                                 AS tokens_out,
    avg(confidence)                                                 AS mean_confidence,
    count(*) FILTER (
        WHERE (citation_report->>'has_fabricated_citations')::boolean IS TRUE
    )                                                               AS fabricated
  FROM traces
 WHERE created_at >= $1
   AND ($2::text IS NULL OR tenant_id = $2)
"""

_BY_TENANT_SQL = """
SELECT tenant_id,
       count(*)                                                     AS requests,
       count(*) FILTER (WHERE action = 'escalated')                 AS escalated,
       count(*) FILTER (WHERE cache_status IN ('exact_hit','semantic_hit')) AS cache_hits,
       sum(virtual_cost_usd)                                        AS cost,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms)       AS p95_total
  FROM traces
 WHERE created_at >= $1
   AND ($2::text IS NULL OR tenant_id = $2)
   AND tenant_id IS NOT NULL
 GROUP BY tenant_id
 ORDER BY requests DESC
"""

_BY_ACTION_SQL = """
SELECT action, count(*) AS n
  FROM traces
 WHERE created_at >= $1 AND ($2::text IS NULL OR tenant_id = $2)
 GROUP BY action
"""

_FEEDBACK_SQL = """
SELECT count(*) FILTER (WHERE rating = 1)  AS up,
       count(*) FILTER (WHERE rating = -1) AS down
  FROM feedback
 WHERE created_at >= $1 AND ($2::text IS NULL OR tenant_id = $2)
"""

_ESCALATION_SQL = """
SELECT reason, status, count(*) AS n
  FROM escalations
 WHERE created_at >= $1 AND ($2::text IS NULL OR tenant_id = $2)
 GROUP BY reason, status
"""
