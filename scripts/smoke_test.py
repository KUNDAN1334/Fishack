"""Pre-flight check: verify every piece of infrastructure and every
configured free LLM provider BEFORE building features on top.

Checks, in order:
  1. Postgres reachable + pgvector extension installed + migrations applied
  2. Redis reachable
  3. Each configured provider individually (tiny completion, ~10 tokens)
  4. The full fallback chain end-to-end
  5. Budget counters actually recorded the calls

Usage:
  python scripts/smoke_test.py             # everything
  python scripts/smoke_test.py --skip-llm  # infra only (no quota spent)

Exit code 0 = ready to build; 1 = something needs fixing (message says what).
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm.base import ChatMessage, ProviderError  # noqa: E402
from app.llm.budget import BudgetTracker  # noqa: E402
from app.llm.client import AllProvidersFailedError, LLMClient, build_providers  # noqa: E402
from app.llm.rate_limit import RetryPolicy  # noqa: E402

PING_MESSAGES = [ChatMessage(role="user", content="Reply with exactly one word: ok")]


def status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


async def check_postgres(settings) -> bool:
    try:
        conn = await asyncpg.connect(settings.database_url, timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] postgres: cannot connect ({exc}). Is `docker compose up` running?")
        return False
    try:
        vector = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'chunks'"
        )
        print(f"[{status(bool(vector))}] postgres: connected, pgvector={vector or 'MISSING'}")
        if not tables:
            print("[WARN] schema not applied yet — run: python scripts/migrate.py")
        return bool(vector)
    finally:
        await conn.close()


async def check_redis(settings) -> bool:
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        print("[PASS] redis: connected")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] redis: {exc}")
        return False


async def check_providers(settings, budget: BudgetTracker | None) -> int:
    """Test each configured provider ALONE (no chain) so a healthy primary
    can't hide a broken fallback. Returns count of working providers."""
    providers = build_providers(settings)
    ok_count = 0
    print(f"\nProvider chain (from LLM_PROVIDER_ORDER): {[p.name for p in providers]}")
    for provider in providers:
        if not provider.is_configured():
            print(f"[SKIP] {provider.name}: not configured (no key / not enabled)")
            continue
        started = time.monotonic()
        try:
            response = await provider.complete(PING_MESSAGES, temperature=0.0, max_tokens=10)
            ms = int((time.monotonic() - started) * 1000)
            if budget:
                await budget.record(response.provider, response.model, response.usage)
            print(
                f"[PASS] {provider.name}: {ms}ms  model={response.model}  "
                f"tokens={response.usage.input_tokens}+{response.usage.output_tokens}  "
                f"reply={response.text.strip()[:40]!r}"
            )
            ok_count += 1
        except ProviderError as exc:
            print(f"[FAIL] {provider.name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {provider.name}: unexpected {type(exc).__name__}: {exc}")
    return ok_count


async def check_chain(settings, budget: BudgetTracker | None) -> bool:
    """One call through the real fallback chain (what the app actually uses)."""
    try:
        client = LLMClient(
            build_providers(settings),
            budget=budget,
            retry_policy=RetryPolicy(max_attempts=2, base_delay=0.5),
        )
    except ValueError as exc:
        print(f"[FAIL] chain: {exc}")
        return False
    try:
        response = await client.complete(PING_MESSAGES, max_tokens=10)
        failovers = len(response.failover_events)
        print(
            f"[PASS] chain: answered by {response.provider} "
            f"({failovers} failover{'s' if failovers != 1 else ''})  "
            f"virtual_cost=${response.virtual_cost_usd:.6f}"
        )
        return True
    except AllProvidersFailedError as exc:
        print(f"[FAIL] chain: {exc}")
        for event in exc.failover_events:
            print(f"       {event['provider']}: {event['error_type']}: {event['error'][:120]}")
        return False


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-llm", action="store_true", help="infra checks only")
    args = parser.parse_args()

    settings = get_settings()
    print("=== Fishack smoke test ===\n")

    pg_ok = await check_postgres(settings)
    redis_ok = await check_redis(settings)

    if args.skip_llm:
        return 0 if (pg_ok and redis_ok) else 1

    budget = None
    if redis_ok:
        budget = BudgetTracker(aioredis.from_url(settings.redis_url))

    providers_ok = await check_providers(settings, budget)
    chain_ok = await check_chain(settings, budget) if providers_ok else False

    if budget:
        print("\nToday's budget counters (feeds /stats in Phase 5):")
        for provider, fields in (await budget.snapshot()).items():
            print(f"  {provider}: {fields}")
        await budget.redis.aclose()

    print(
        f"\nResult: postgres={status(pg_ok)} redis={status(redis_ok)} "
        f"providers_ok={providers_ok} chain={status(chain_ok)}"
    )
    if not (pg_ok and redis_ok and chain_ok):
        return 1
    print("All green — safe to build on top.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
