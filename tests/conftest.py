"""Shared fixtures — chiefly the database ones.

Most of Fishly's suite is pure and runs anywhere. Retrieval is not: the whole
point of Phase 2 is SQL, and SQL that is never executed is a hypothesis. So a
handful of tests need a live Postgres with pgvector.

Those tests are marked `integration` and SKIP (never fail) when the database
is unreachable, so `pytest -q` stays green on a laptop with Docker stopped.
CI runs them with the compose stack up — and the tenant-leakage test in
particular must run on every push, which is why the fixtures below build
their own tiny corpus with fake embeddings instead of depending on the real
ingested one. A test that requires a 20-minute ingest is a test that quietly
stops running.
"""

from __future__ import annotations

import asyncpg
import pytest

from app.config import get_settings
from tests.fakes import FakeEncoder

# Throwaway tenants. Deliberately NOT 'acme'/'globex': these fixtures delete
# everything they create, and pointing that cleanup at your real corpus once
# is one time too many.
TENANT_A = "test_tenant_a"
TENANT_B = "test_tenant_b"

# A token that must exist ONLY in tenant B's corpus. The leakage test asserts
# it never appears in tenant A's results — and, crucially, that it IS findable
# without the tenant filter (see test_tenant_isolation.py on vacuous passes).
SENTINEL = "zzsentinel_tenantb_only"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: requires a live Postgres with pgvector (docker compose up -d)"
    )


@pytest.fixture
async def db_pool():
    """A pool against the configured database, or a skip with a useful hint."""
    settings = get_settings()
    try:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url, min_size=1, max_size=4, timeout=3.0
        )
    except Exception as exc:  # noqa: BLE001 — any connection problem means skip
        pytest.skip(
            f"no database at {settings.database_url} ({type(exc).__name__}). "
            "Start it with: docker compose up -d postgres redis"
        )

    try:
        async with pool.acquire() as conn:
            has_chunks = await conn.fetchval("SELECT to_regclass('public.chunks')")
        if has_chunks is None:
            pytest.skip("database reachable but not migrated — run: python scripts/migrate.py")
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def seeded_corpus(db_pool):
    """Two tenants with deliberately SIMILAR content, one carrying a sentinel.

    The similarity is the design: if tenant B held nothing relevant to the
    test query, an isolation test would pass even with the filter removed.
    Both tenants therefore hold near-identical webhook documentation, so the
    only thing keeping B's rows out of A's results is the tenant predicate
    itself.
    """
    encoder = FakeEncoder()

    documents = [
        # (tenant, source_type, title, path, chunks)
        (
            TENANT_A, "docs", "Webhooks Overview", "test/a/webhooks.md",
            [
                ("Webhooks > Retry Logic",
                 "Webhooks > Retry Logic\n\nWebhook deliveries are retried up to 3 times "
                 "with exponential backoff. Failed deliveries return ERR_TIMEOUT_502."),
                ("Webhooks > Signatures",
                 "Webhooks > Signatures\n\nEvery webhook payload is signed with an HMAC "
                 "signature in the X-Flowlytics-Signature header."),
            ],
        ),
        (
            TENANT_A, "changelog", "v2.3 release", "test/a/changelog.jsonl",
            [(None, "v2.3 (2026-06-10) — Increased the webhook retry limit from 3 to 5 attempts.")],
        ),
        (
            TENANT_B, "docs", "Webhooks Overview", "test/b/webhooks.md",
            [
                ("Webhooks > Retry Logic",
                 f"Webhooks > Retry Logic\n\nWebhook deliveries are retried up to 3 times "
                 f"with exponential backoff. Failed deliveries return ERR_TIMEOUT_502. "
                 f"Internal reference {SENTINEL}."),
            ],
        ),
    ]

    async with db_pool.acquire() as conn:
        for tenant in (TENANT_A, TENANT_B):
            await conn.execute(
                "INSERT INTO tenants (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                tenant, f"Test tenant {tenant}",
            )
        # Clean slate in case a previous run died before its teardown.
        await conn.execute(
            "DELETE FROM documents WHERE tenant_id = ANY($1::text[])", [TENANT_A, TENANT_B]
        )

        for tenant, source_type, title, path, chunk_specs in documents:
            document_id = await conn.fetchval(
                """
                INSERT INTO documents (
                    tenant_id, source_type, title, source_path, doc_version,
                    effective_date, product_area, content_hash, is_current
                )
                VALUES ($1, $2, $3, $4, 'v2.3', DATE '2026-06-10', 'platform', $5, true)
                RETURNING id
                """,
                tenant, source_type, title, path, f"hash-{tenant}-{path}",
            )
            for index, (heading_path, content) in enumerate(chunk_specs):
                vector = encoder.encode_passages([content])[0]
                await conn.execute(
                    """
                    INSERT INTO chunks (
                        document_id, tenant_id, chunk_index, content, content_hash,
                        heading_path, token_count, metadata, embedding, is_current
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, '{}'::jsonb, $8::vector, true)
                    """,
                    document_id, tenant, index, content,
                    f"chunkhash-{tenant}-{path}-{index}", heading_path,
                    len(content) // 4, _format_vector(vector),
                )

    yield {"encoder": encoder, "tenant_a": TENANT_A, "tenant_b": TENANT_B, "sentinel": SENTINEL}

    async with db_pool.acquire() as conn:
        # chunks cascade from documents; tenants go last (FK targets).
        await conn.execute(
            "DELETE FROM documents WHERE tenant_id = ANY($1::text[])", [TENANT_A, TENANT_B]
        )
        await conn.execute("DELETE FROM tenants WHERE id = ANY($1::text[])", [TENANT_A, TENANT_B])


def _format_vector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"
