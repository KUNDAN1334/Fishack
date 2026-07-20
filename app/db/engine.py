"""Postgres connection management.

One asyncpg pool per process, created at app startup (see main.py lifespan)
and injected everywhere else — no module-level global connections, so tests
can construct pools against test databases.
"""

import asyncpg


async def create_pool(database_url: str, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Create the shared connection pool.

    max_size=10: solo-dev scale. PRODUCTION NOTE: at real load you'd size
    this against Postgres max_connections / number of API replicas, and put
    pgbouncer in front for transaction pooling.
    """
    return await asyncpg.create_pool(dsn=database_url, min_size=min_size, max_size=max_size)


async def check_database(pool: asyncpg.Pool) -> dict:
    """Health probe used by /health and smoke_test.py.

    Verifies both connectivity AND that the pgvector extension is installed —
    a reachable Postgres without pgvector would fail much later (first
    ingest) with a confusing error, so we check it up front.
    """
    async with pool.acquire() as conn:
        server_version = await conn.fetchval("SHOW server_version")
        vector_version = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
    return {
        "postgres_version": server_version,
        "pgvector_version": vector_version,  # None => extension missing
        "pgvector_installed": vector_version is not None,
    }
