"""The chunking before/after experiment (Design.md §4, ADR-021).

    "End-to-end demo of one measured improvement: run baseline with naive
     fixed-size chunking -> switch to the per-source chunking strategy -> show
     the metric delta in a table in the README."

    python scripts/chunking_experiment.py ingest    # build the naive shadow tenants
    python scripts/chunking_experiment.py compare   # run both arms, print the table
    python scripts/chunking_experiment.py clean     # remove the shadow tenants

METHOD: shadow tenants. The same corpus is ingested a second time under
`acme_naive` / `globex_naive` using `NaiveChunker`, and identical retrieval
metrics are run against both. Three reasons this is the right shape:

  * It reuses the entire pipeline unchanged — same embeddings, same retrieval,
    same metrics. The ONLY variable is the chunker, which is what an
    experiment is supposed to isolate.
  * Tenant isolation (ADR-012) guarantees the arms cannot contaminate each
    other. The mechanism protecting customers also protects the experiment.
  * Both arms exist at once, so the comparison can be re-run without a full
    re-ingest cycle.

WHY THIS ONLY WORKS BECAUSE OF ADR-019. Ground truth is stored as stable
locators ("the Retry Logic section of webhooks-overview"), not chunk ids. The
naive arm produces entirely different chunks with different ids, so an eval
keyed on chunk UUIDs could not compare the two arms at all — it would be
scoring the naive arm against ground truth expressed in the smart arm's
artifacts. This is the payoff for a decision that looked like bookkeeping.

A CAVEAT WORTH STATING IN THE README. Naive chunks carry no `heading_path` and
no per-source metadata, so docs locators resolve by `source_path` alone and
match EVERY chunk of that page rather than one section. That inflates the
naive arm's recall (more chunks count as correct), which means the measured
delta is a LOWER BOUND on the real improvement. Better to understate a result
than to explain away an overstated one.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.ingestion.chunkers.naive import NaiveChunker  # noqa: E402
from app.ingestion.pipeline import IngestionPipeline  # noqa: E402
from app.ingestion.tokenizer import get_token_counter  # noqa: E402
from app.retrieval.service import build_retrieval_service  # noqa: E402
from app.retrieval.tenant_scope import TenantScope  # noqa: E402
from fishnet.metrics import summarize  # noqa: E402
from fishnet.models import load_cases  # noqa: E402
from fishnet.resolver import resolve_all  # noqa: E402
from fishnet.metrics import case_metrics  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
GOLDEN = ROOT / "data" / "golden" / "golden_set.jsonl"

SHADOW_SUFFIX = "_naive"
BASE_TENANTS = ("acme", "globex")
METRICS = ["recall@5", "recall@20", "precision@5", "mrr"]


def shadow(tenant: str) -> str:
    return f"{tenant}{SHADOW_SUFFIX}"


class NaiveIngestionPipeline(IngestionPipeline):
    """The standard pipeline with the chunker swapped.

    Subclassing rather than adding a flag to IngestionPipeline: the production
    pipeline should have no code path that produces naive chunks. A `if
    self.naive:` branch in the real ingester is a footgun that will eventually
    fire in production, and the experiment does not need it.
    """

    def _get_chunker(self, source_type: str):  # type: ignore[override]
        # Every source type gets the same chunker — that IS the naive
        # strategy, and the thing Design.md §4 argues against.
        return NaiveChunker(self.tokens)


async def cmd_ingest(args, pool: asyncpg.Pool) -> int:
    settings = get_settings()
    encoder = get_encoder(settings.embedding_model_name)
    pipeline = NaiveIngestionPipeline(
        pool=pool,
        embeddings=EmbeddingService(pool, encoder),
        token_counter=get_token_counter(settings.embedding_model_name),
    )

    for tenant in BASE_TENANTS:
        target = shadow(tenant)
        print(f"\n=== ingesting {target} (naive fixed-size chunking) ===")
        # Same source files, different tenant, different chunker. The
        # embedding cache is shared and keyed by (model, text), so any chunk
        # whose text happens to match is embedded once across both arms —
        # which makes the second ingest much cheaper than the first.
        result = await pipeline.ingest_tenant(RAW_DIR, tenant, f"{target} (naive)", force=True,
                                              tenant_override=target)
        print(
            f"  documents {result.documents_ingested}  chunks {result.chunks_written}  "
            f"embeddings computed {result.embeddings_computed} "
            f"(cached {result.embeddings_from_cache})"
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tenant_id, count(*) AS chunks, round(avg(token_count)) AS avg_tokens
              FROM chunks WHERE is_current GROUP BY tenant_id ORDER BY tenant_id
            """
        )
    print("\ncorpus comparison:")
    for row in rows:
        print(f"  {row['tenant_id']:<16} {row['chunks']:>5} chunks  avg {row['avg_tokens']} tokens")
    return 0


async def cmd_compare(args, pool: asyncpg.Pool) -> int:
    """Run identical retrieval metrics against both arms.

    Retrieval-only, deliberately: no LLM calls at all. The experiment is about
    CHUNKING, which is a retrieval-quality question, and involving generation
    would add judge noise and quota limits to a measurement that does not need
    either.
    """
    settings = get_settings()
    cases = load_cases(GOLDEN)
    # Cases whose ground truth is "retrieve nothing" cannot distinguish two
    # chunking strategies — both arms score 1.0 by construction. Excluded so
    # they do not dilute the delta toward zero.
    cases = [c for c in cases if c.expected_sources]
    print(f"{len(cases)} cases with expected sources")

    encoder = get_encoder(settings.embedding_model_name)
    embeddings = EmbeddingService(pool, encoder)
    service = build_retrieval_service(embeddings, settings, with_reranker=not args.no_rerank)

    arms: dict[str, dict[str, dict[str, float]]] = {}

    for arm, suffix in (("smart (per-source)", ""), ("naive (fixed-size)", SHADOW_SUFFIX)):
        # Rewrite each case onto the arm's tenant, then resolve locators
        # against THAT corpus — this is the step chunk-id ground truth could
        # not do (ADR-019).
        arm_cases = [c.model_copy(update={"tenant_id": c.tenant_id + suffix}) for c in cases]
        resolved, warnings = await resolve_all(pool, arm_cases)
        usable = [r for r in resolved if r.expected_chunk_ids]
        if not usable:
            print(f"\n{arm}: no resolvable cases — has the corpus been ingested?")
            continue

        per_case = []
        for item in usable:
            scope = TenantScope(pool, item.case.tenant_id)
            retrieval = await service.retrieve(
                scope, item.case.query, mode="hybrid",
                top_k=settings.retrieval_fusion_top_k,
            )
            ordered = [scored.chunk.chunk_id for scored in retrieval.candidates]
            per_case.append((item.case.case_type, case_metrics(ordered, item.expected_chunk_ids)))

        arms[arm] = summarize(per_case)
        print(f"  {arm}: scored {len(usable)}/{len(arm_cases)} cases "
              f"({len(warnings)} with unresolved locators)")

    if len(arms) < 2:
        print("\nNeed both arms. Run: python scripts/chunking_experiment.py ingest")
        return 1

    print_table(arms)
    return 0


def print_table(arms: dict[str, dict[str, dict[str, float]]]) -> None:
    smart, naive = "smart (per-source)", "naive (fixed-size)"
    width = 96

    print("\n" + "=" * width)
    print("CHUNKING EXPERIMENT — naive fixed-size vs per-source strategies")
    print("=" * width)
    header = f"{'case type':<20}" + "".join(f"{m:>13}" for m in METRICS)
    print(f"\n{header}")
    print("-" * width)

    groups = ["overall"] + sorted(k for k in arms[smart] if k != "overall")
    for group in groups:
        if group not in arms[smart] or group not in arms[naive]:
            continue
        naive_row = "".join(f"{arms[naive][group].get(m, 0.0):>13.3f}" for m in METRICS)
        smart_row = "".join(f"{arms[smart][group].get(m, 0.0):>13.3f}" for m in METRICS)
        delta_row = "".join(
            f"{arms[smart][group].get(m, 0.0) - arms[naive][group].get(m, 0.0):>+13.3f}"
            for m in METRICS
        )
        label = "OVERALL" if group == "overall" else group
        print(f"{label:<20}")
        print(f"  {'naive':<18}{naive_row}")
        print(f"  {'per-source':<18}{smart_row}")
        print(f"  {'delta':<18}{delta_row}")
        print()

    print("=" * width)
    print("Note: naive chunks carry no heading_path, so docs locators resolve to EVERY")
    print("chunk of a page rather than one section. That inflates the naive arm's recall,")
    print("making this delta a LOWER BOUND on the real improvement.")
    print("=" * width)


async def cmd_clean(args, pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        for tenant in BASE_TENANTS:
            target = shadow(tenant)
            # chunks cascade from documents; the embedding cache is kept
            # because it is model-keyed and reusable.
            await conn.execute("DELETE FROM documents WHERE tenant_id = $1", target)
            await conn.execute("DELETE FROM tenants WHERE id = $1", target)
            print(f"removed shadow tenant {target}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="build the naive shadow tenants")
    p_compare = sub.add_parser("compare", help="run both arms and print the table")
    p_compare.add_argument("--no-rerank", action="store_true")
    sub.add_parser("clean", help="remove the shadow tenants")
    args = parser.parse_args()

    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        handlers = {"ingest": cmd_ingest, "compare": cmd_compare, "clean": cmd_clean}
        return await handlers[args.command](args, pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
