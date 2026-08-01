"""Retrieval playground: type a query, see every method side by side.

    python scripts/retrieval_playground.py --tenant acme
    python scripts/retrieval_playground.py --query "webhook retry limit"
    python scripts/retrieval_playground.py --query "ERR_TIMEOUT_502" --explain
    python scripts/retrieval_playground.py --no-rerank        # skip loading 280MB

This script is the Phase 2 equivalent of `ingest.py inspect`: retrieval
quality is invisible until you look at actual ranked lists for actual
queries. Reading four columns for a dozen real questions will teach you more
about why hybrid retrieval matters than any metric — and it is how you build
intuition for which cases belong in the Phase 4 golden set.

What to look for:
  * A query with an exact identifier (ERR_TIMEOUT_502, v2.3). BM25 should
    nail it; vector search will drift toward "connection error" docs.
  * A natural-language query with no shared vocabulary ("why isn't my data
    showing up"). Vector should win; BM25 may return nothing at all.
  * The hybrid column: chunks marked [both] are the ones RRF promoted for
    agreement. That promotion IS the value of fusion.
  * The reranked column against hybrid: what moved, and does the move look
    right to you? Disagreement here is the most interesting thing on screen.

`--explain` prints the tsquery Postgres actually built, which is how you find
out what the FTS parser does with underscores and version numbers.
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
from app.retrieval.models import RetrievalResult, ScoredChunk  # noqa: E402
from app.retrieval.service import build_retrieval_service  # noqa: E402
from app.retrieval.tenant_scope import TenantScope  # noqa: E402

# The playground is a reading tool; INFO logs from the legs would interleave
# with the tables and make them unreadable. Warnings still get through.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

COLUMN_WIDTH = 92


def label(scored: ScoredChunk) -> str:
    """One line describing a result: where it came from and what it says."""
    chunk = scored.chunk
    where = chunk.heading_path or chunk.title or chunk.source_path
    body = " ".join(chunk.content.split())
    if chunk.heading_path and body.startswith(chunk.heading_path):
        body = body[len(chunk.heading_path):].strip()
    return f"{chunk.source_type}/{where} — {body}"


def print_ranking(title: str, items: list[ScoredChunk], score_of, annotate=None) -> None:
    print(f"\n{title}")
    print("-" * COLUMN_WIDTH)
    if not items:
        print("  (nothing)")
        return
    for position, scored in enumerate(items, start=1):
        note = f" {annotate(scored)}" if annotate else ""
        print(f"  {position:>2}. [{score_of(scored):>7.4f}] {scored.chunk.chunk_id[:8]}{note}")
        text = label(scored)
        print(f"      {text[:COLUMN_WIDTH - 6]}")


def hybrid_annotation(scored: ScoredChunk) -> str:
    """Show WHICH legs found each chunk — the whole story of the fusion."""
    if scored.found_by_both_legs:
        return f"[both  b{scored.bm25_rank:<2} v{scored.vector_rank:<2}]"
    if scored.bm25_rank is not None:
        return f"[bm25  b{scored.bm25_rank:<2}    ]"
    return f"[vector    v{scored.vector_rank:<2}]"


def rerank_annotation(hybrid_positions: dict[str, int]):
    """Show how far the reranker moved each chunk relative to fusion order."""

    def annotate(scored: ScoredChunk) -> str:
        was = hybrid_positions.get(scored.chunk.chunk_id)
        if was is None:
            return "[new to top]"
        moved = was - (scored.rerank_rank or 0)
        if moved > 0:
            return f"[up {moved} from #{was}]"
        if moved < 0:
            return f"[down {-moved} from #{was}]"
        return "[unchanged]"

    return annotate


def print_summary(hybrid: RetrievalResult, reranked: RetrievalResult | None) -> None:
    print("\n" + "=" * COLUMN_WIDTH)
    legs = "  ".join(
        f"{leg.leg}={leg.elapsed_ms}ms({len(leg.chunk_ids)})" + ("  ERROR" if not leg.ok else "")
        for leg in hybrid.legs
    )
    print(f"timings   embed={hybrid.embed_ms}ms  {legs}  total={hybrid.total_ms}ms")

    if hybrid.degraded_legs:
        print(f"DEGRADED  legs failed and were skipped: {hybrid.degraded_legs}")

    both = sum(1 for candidate in hybrid.candidates if candidate.found_by_both_legs)
    print(f"overlap   {both}/{len(hybrid.candidates)} fused candidates were found by BOTH legs")

    if reranked and reranked.rerank:
        decision = reranked.rerank
        margin = f"{decision.margin:.3f}" if decision.margin is not None else "n/a"
        print(
            f"rerank    ran={decision.reranked}  reason={decision.reason}  "
            f"margin={margin} (threshold {decision.threshold})  {reranked.rerank_ms}ms"
        )
    print("=" * COLUMN_WIDTH)


async def explain_tsquery(pool: asyncpg.Pool, query: str) -> None:
    """Show what Postgres full-text search actually does with this query.

    The reason this exists: it is very easy to assume `ERR_TIMEOUT_502` is one
    searchable token. Postgres's default parser has opinions about
    underscores, digits, and hyphens, and those opinions decide whether the
    BM25 leg can do exact-identifier matching at all.
    """
    async with pool.acquire() as conn:
        tsquery = await conn.fetchval("SELECT websearch_to_tsquery('english', $1)::text", query)
        tsvector = await conn.fetchval("SELECT to_tsvector('english', $1)::text", query)
        tokens = await conn.fetch(
            "SELECT alias, token FROM ts_debug('english', $1) WHERE lexemes IS NOT NULL", query
        )

    print("\n--- how Postgres FTS sees this query -------------------------------------")
    print(f"  to_tsvector          : {tsvector}")
    print(f"  websearch_to_tsquery : {tsquery}")
    print("  parser tokens        : " + ", ".join(f"{r['token']}({r['alias']})" for r in tokens))
    print("  (a multi-lexeme identifier means BM25 matches its PARTS, not the whole)")


async def run_query(pool: asyncpg.Pool, services, tenant: str, query: str, args) -> None:
    plain, with_reranker = services
    scope = TenantScope(pool, tenant)

    if args.explain:
        await explain_tsquery(pool, query)

    # Each mode goes through the same RetrievalService — that is the point.
    bm25_only = await plain.retrieve(scope, query, mode="bm25", top_k=args.top)
    vector_only = await plain.retrieve(scope, query, mode="vector", top_k=args.top)
    hybrid = await plain.retrieve(scope, query, mode="hybrid", top_k=args.top)

    print(f"\n{'=' * COLUMN_WIDTH}\nQUERY: {query!r}   tenant={tenant}\n{'=' * COLUMN_WIDTH}")

    print_ranking("1) BM25 only (Postgres FTS)", bm25_only.results, lambda s: s.bm25_score or 0.0)
    print_ranking("2) Vector only (pgvector cosine)", vector_only.results,
                  lambda s: s.vector_score or 0.0)
    print_ranking("3) Hybrid (RRF fusion)", hybrid.results, lambda s: s.fused_score,
                  annotate=hybrid_annotation)

    reranked = None
    if with_reranker is not None:
        reranked = await with_reranker.retrieve(scope, query, mode="hybrid", top_k=args.top)
        hybrid_positions = {s.chunk.chunk_id: s.fused_rank for s in hybrid.candidates}
        if reranked.rerank and reranked.rerank.reranked:
            print_ranking("4) Reranked (bge-reranker-base cross-encoder)", reranked.results,
                          lambda s: s.rerank_score or 0.0,
                          annotate=rerank_annotation(hybrid_positions))
        else:
            reason = reranked.rerank.reason if reranked.rerank else "unknown"
            print(f"\n4) Reranked — SKIPPED ({reason})\n{'-' * COLUMN_WIDTH}")

    print_summary(hybrid, reranked)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tenant", default="acme")
    parser.add_argument("--query", help="run one query and exit (otherwise: interactive)")
    parser.add_argument("--top", type=int, default=5, help="results per column")
    parser.add_argument("--no-rerank", action="store_true",
                        help="skip loading the cross-encoder (much faster startup)")
    parser.add_argument("--explain", action="store_true",
                        help="show the tsquery Postgres builds for each query")
    args = parser.parse_args()

    settings = get_settings()
    pool = await create_pool(settings.database_url)

    try:
        async with pool.acquire() as conn:
            chunk_count = await conn.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant_id = $1 AND is_current", args.tenant
            )
        if not chunk_count:
            print(
                f"No current chunks for tenant {args.tenant!r}. "
                "Run: python scripts/ingest.py run"
            )
            return 1
        print(f"tenant {args.tenant}: {chunk_count} current chunks")

        encoder = get_encoder(settings.embedding_model_name)
        embeddings = EmbeddingService(pool, encoder)

        # Two services: one without a reranker for the single-leg and fusion
        # columns, one with. Building them separately keeps the fusion columns
        # honest — they show the fusion order, never a silently reranked one.
        plain = build_retrieval_service(embeddings, settings, with_reranker=False)
        with_reranker = None
        if not args.no_rerank and settings.reranker_enabled:
            print("loading cross-encoder (first run downloads ~280MB)...")
            with_reranker = build_retrieval_service(embeddings, settings, with_reranker=True)

        services = (plain, with_reranker)

        if args.query:
            await run_query(pool, services, args.tenant, args.query, args)
            return 0

        print("\nType a query and press Enter. Ctrl-C or an empty line to quit.")
        while True:
            try:
                query = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not query:
                return 0
            try:
                await run_query(pool, services, args.tenant, query, args)
            except Exception as exc:  # noqa: BLE001 — a REPL must survive one bad query
                print(f"ERROR: {type(exc).__name__}: {exc}")
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
