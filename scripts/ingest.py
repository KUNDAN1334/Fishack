"""Ingestion CLI: load the corpus into Postgres, then inspect what landed.

    python scripts/ingest.py run                    # ingest all tenants
    python scripts/ingest.py run --tenant acme      # one tenant
    python scripts/ingest.py run --force            # re-chunk unchanged docs
    python scripts/ingest.py stats                  # per-tenant/source counts
    python scripts/ingest.py inspect --tenant acme --source docs --limit 5
    python scripts/ingest.py inspect --chunk-id <uuid>
    python scripts/ingest.py conflicts --tenant acme
    python scripts/ingest.py reset --tenant acme    # wipe that tenant's data

The `inspect` command is the point of this phase: chunking decisions are
invisible until you read actual chunks. Look at boundaries, heading
prefixes, and token counts before trusting any retrieval numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.ingestion import repository  # noqa: E402
from app.ingestion.pipeline import IngestionPipeline  # noqa: E402
from app.ingestion.tokenizer import get_token_counter  # noqa: E402
from data.generation.spec import TENANTS  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest")


async def cmd_run(args, pool: asyncpg.Pool) -> int:
    settings = get_settings()
    encoder = get_encoder(settings.embedding_model_name)

    if encoder.dimension != settings.embedding_dim:
        # Fail before writing anything: a dimension mismatch against the
        # vector(384) column would fail per-row later, after minutes of work.
        print(
            f"ERROR: model {settings.embedding_model_name} produces "
            f"{encoder.dimension} dims but config/schema expect {settings.embedding_dim}. "
            f"See ADR-005 — changing models needs a migration + full re-ingest."
        )
        return 1

    pipeline = IngestionPipeline(
        pool=pool,
        embeddings=EmbeddingService(pool, encoder),
        token_counter=get_token_counter(settings.embedding_model_name),
    )

    tenants = [args.tenant] if args.tenant else list(TENANTS)
    for tenant in tenants:
        if tenant not in TENANTS:
            print(f"Unknown tenant {tenant!r}. Known: {list(TENANTS)}")
            return 1
        print(f"\n=== Ingesting {tenant} ===")
        result = await pipeline.ingest_tenant(RAW_DIR, tenant, TENANTS[tenant], force=args.force)
        print(
            f"  documents ingested : {result.documents_ingested}\n"
            f"  skipped (duplicate): {result.documents_skipped_duplicate}\n"
            f"  archived/superseded: {result.documents_superseded}\n"
            f"  chunks written     : {result.chunks_written}\n"
            f"  embeddings computed: {result.embeddings_computed}\n"
            f"  embeddings cached  : {result.embeddings_from_cache}"
        )
        for error in result.errors:
            print(f"  ERROR: {error}")
    return 0


async def cmd_stats(args, pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        rows = await repository.corpus_stats(conn)
        totals = await conn.fetchrow(
            """
            SELECT count(*) AS chunks,
                   count(*) FILTER (WHERE is_current) AS current,
                   count(*) FILTER (WHERE embedding IS NULL) AS unembedded
              FROM chunks
            """
        )
        cache_size = await conn.fetchval("SELECT count(*) FROM embedding_cache")

    if not rows:
        print("No data. Run: python scripts/ingest.py run")
        return 0

    header = f"{'tenant':<8} {'source':<10} {'docs':>5} {'chunks':>7} {'current':>8} {'avg tok':>8} {'min':>5} {'max':>5}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['tenant_id']:<8} {row['source_type']:<10} {row['documents']:>5} "
            f"{row['chunks']:>7} {row['current_chunks']:>8} {str(row['avg_tokens'] or '-'):>8} "
            f"{str(row['min_tokens'] or '-'):>5} {str(row['max_tokens'] or '-'):>5}"
        )
    print(
        f"\nTotal chunks: {totals['chunks']} "
        f"({totals['current']} current, {totals['chunks'] - totals['current']} archived)"
    )
    if totals["unembedded"]:
        print(f"WARNING: {totals['unembedded']} chunks have no embedding")
    print(f"Embedding cache entries: {cache_size}")
    return 0


async def cmd_inspect(args, pool: asyncpg.Pool) -> int:
    """Print real chunks. Read these before believing any retrieval metric."""
    async with pool.acquire() as conn:
        if args.chunk_id:
            rows = await conn.fetch(
                """
                SELECT c.*, d.title, d.source_path, d.doc_version, d.effective_date
                  FROM chunks c JOIN documents d ON d.id = c.document_id
                 WHERE c.id = $1
                """,
                args.chunk_id,
            )
        else:
            conditions = ["c.tenant_id = $1"]
            params: list = [args.tenant]
            if args.source:
                params.append(args.source)
                conditions.append(f"d.source_type = ${len(params)}")
            if args.grep:
                params.append(f"%{args.grep}%")
                conditions.append(f"c.content ILIKE ${len(params)}")
            if not args.include_archived:
                conditions.append("c.is_current = true")
            params.append(args.limit)
            rows = await conn.fetch(
                f"""
                SELECT c.*, d.title, d.source_path, d.doc_version, d.effective_date
                  FROM chunks c JOIN documents d ON d.id = c.document_id
                 WHERE {' AND '.join(conditions)}
                 ORDER BY d.source_path, c.chunk_index
                 LIMIT ${len(params)}
                """,
                *params,
            )

    if not rows:
        print("No chunks matched.")
        return 0

    for row in rows:
        print("=" * 78)
        print(f"chunk_id     : {row['id']}")
        print(f"tenant       : {row['tenant_id']}   is_current: {row['is_current']}")
        print(f"document     : {row['title']}  ({row['source_path']})")
        print(f"version/date : {row['doc_version']} / {row['effective_date']}")
        print(f"heading_path : {row['heading_path']}")
        print(f"index/tokens : #{row['chunk_index']}  {row['token_count']} tokens")
        print(f"metadata     : {row['metadata']}")
        print(f"embedded     : {'yes' if row['embedding'] is not None else 'NO'}")
        print("-" * 78)
        content = row["content"]
        print(content if args.full else content[:700] + ("..." if len(content) > 700 else ""))
    print("=" * 78)
    print(f"{len(rows)} chunk(s)")
    return 0


async def cmd_conflicts(args, pool: asyncpg.Pool) -> int:
    """Show the planted stale-data situations — the Phase 4 eval cases."""
    async with pool.acquire() as conn:
        archived = await conn.fetch(
            """
            SELECT title, source_path, doc_version, effective_date
              FROM documents
             WHERE tenant_id = $1 AND is_current = false
             ORDER BY source_path
            """,
            args.tenant,
        )
        tagged = await conn.fetch(
            """
            SELECT c.id, d.title, c.heading_path,
                   c.metadata->>'conflicts_with_entry' AS entry_id
              FROM chunks c JOIN documents d ON d.id = c.document_id
             WHERE c.tenant_id = $1 AND c.metadata ? 'conflicts_with_entry'
             ORDER BY d.title, c.chunk_index
            """,
            args.tenant,
        )

    print(f"--- Archived (superseded, is_current=false) — {len(archived)} documents ---")
    for row in archived:
        print(f"  {row['title']:<40} {row['doc_version']:<6} {row['effective_date']}  {row['source_path']}")

    print(f"\n--- Live but contested (unmarked conflict) — {len(tagged)} chunks ---")
    for row in tagged:
        print(f"  {row['title']:<40} {str(row['heading_path'])[:32]:<34} contested by {row['entry_id']}")
    print("\nThe second group is the interesting one: both the old doc and the newer")
    print("changelog are retrievable, so generation must prefer the newest and flag it.")
    return 0


async def cmd_reset(args, pool: asyncpg.Pool) -> int:
    """Wipe one tenant's documents/chunks. Embedding cache is kept — it's
    model-keyed and reusable, so re-ingesting costs no model compute."""
    if not args.yes:
        confirm = input(f"Delete ALL documents and chunks for tenant {args.tenant!r}? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return 0
    async with pool.acquire() as conn:
        # chunks cascade from documents (ON DELETE CASCADE)
        deleted = await conn.execute("DELETE FROM documents WHERE tenant_id = $1", args.tenant)
    print(f"Deleted documents for {args.tenant}: {deleted}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="ingest the corpus")
    p_run.add_argument("--tenant")
    p_run.add_argument("--force", action="store_true",
                       help="re-chunk and re-embed even if content is unchanged")

    sub.add_parser("stats", help="per-tenant/source counts and token distribution")

    p_inspect = sub.add_parser("inspect", help="print real chunks")
    p_inspect.add_argument("--tenant", default="acme")
    p_inspect.add_argument("--source", choices=["docs", "changelog", "ticket"])
    p_inspect.add_argument("--grep", help="only chunks whose content contains this")
    p_inspect.add_argument("--chunk-id")
    p_inspect.add_argument("--limit", type=int, default=3)
    p_inspect.add_argument("--full", action="store_true", help="do not truncate content")
    p_inspect.add_argument("--include-archived", action="store_true")

    p_conflicts = sub.add_parser("conflicts", help="show planted stale-data cases")
    p_conflicts.add_argument("--tenant", default="acme")

    p_reset = sub.add_parser("reset", help="delete a tenant's ingested data")
    p_reset.add_argument("--tenant", required=True)
    p_reset.add_argument("--yes", action="store_true")

    args = parser.parse_args()
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        handlers = {
            "run": cmd_run, "stats": cmd_stats, "inspect": cmd_inspect,
            "conflicts": cmd_conflicts, "reset": cmd_reset,
        }
        return await handlers[args.command](args, pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
