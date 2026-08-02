"""The eval CLI (Design.md §12, free-tier requirement #3).

    python -m fishnet.run                       full run, all arms
    python -m fishnet.run --sample 10           quick smoke during development
    python -m fishnet.run --resume <run_id>     continue a run that hit a quota wall
    python -m fishnet.run --retrieval-only      no LLM calls at all
    python -m fishnet.run --arms hybrid,bm25,vector    the comparison table
    python -m fishnet.run --write-baseline      commit this run as the baseline
    python -m fishnet.run --no-judge            skip LLM-as-judge

Three free-tier survival features, and they are features rather than
workarounds — they are what running evals against ANY rate-limited API looks
like:

  --sample N   A 60-case run costs 60 generations plus 60 judgements. During
               development you want the loop to close in a minute, and a
               10-case smoke catches most breakage.

  --resume     A run that dies at case 43 must not throw away 43 cases of
               work. Results are appended to a JSONL checkpoint as each case
               finishes, and --resume skips anything already recorded. This is
               why the checkpoint is written per case rather than at the end.

  concurrency  A hard cap on simultaneous LLM calls. Firing 60 requests at a
               free tier gets every one of them 429'd; the LLM client's
               backoff would then serialize them anyway, but slowly and after
               burning the quota. Better to never send them.

RETRIEVAL RUNS WITHOUT ANY LLM. `--retrieval-only` measures recall, precision
and MRR with zero API calls, which means the metric that matters most is
always available regardless of quota — and it is the arm the chunking
experiment and the comparison table need.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.generation.citations import CitationValidator  # noqa: E402
from app.generation.generator import Generator  # noqa: E402
from app.generation.models import ChatRequest, Turn  # noqa: E402
from app.generation.pipeline import ChatPipeline  # noqa: E402
from app.generation.prompts import build_context_block  # noqa: E402
from app.generation.rewriter import QueryRewriter  # noqa: E402
from app.llm.client import LLMClient, build_providers  # noqa: E402
from app.retrieval.service import build_retrieval_service  # noqa: E402
from app.retrieval.tenant_scope import TenantScope  # noqa: E402
from fishnet import baseline as baseline_module  # noqa: E402
from fishnet import scorecard  # noqa: E402
from fishnet.assertions import run_assertions  # noqa: E402
from fishnet.judge import Judge  # noqa: E402
from fishnet.metrics import case_metrics  # noqa: E402
from fishnet.models import (  # noqa: E402
    CaseResult,
    JudgeScores,
    RetrievalScores,
    RunReport,
    load_cases,
)
from fishnet.resolver import ResolvedCase, resolve_all  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fishnet")

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "data" / "golden" / "golden_set.jsonl"
BASELINE_PATH = ROOT / "data" / "golden" / "baselines" / "baseline.json"
REPORTS_DIR = ROOT / "fishnet_reports"
CHECKPOINT_DIR = REPORTS_DIR / "checkpoints"


def git_sha() -> str | None:
    """Stamped on every report so a scorecard can be traced to the code that
    produced it. A number without a commit is an anecdote."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001 — not a git checkout, or no git
        return None


def config_snapshot(settings: Settings) -> dict:
    """The knobs that materially change results.

    Recorded because comparing two scorecards produced under different
    thresholds is comparing two different systems — and the difference would
    be invisible without this.
    """
    return {
        "embedding_model": settings.embedding_model_name,
        "reranker_model": settings.reranker_model_name,
        "reranker_enabled": settings.reranker_enabled,
        "conditional_rerank_enabled": settings.conditional_rerank_enabled,
        "retrieval_candidates_per_leg": settings.retrieval_candidates_per_leg,
        "retrieval_fusion_top_k": settings.retrieval_fusion_top_k,
        "rerank_input_top_k": settings.rerank_input_top_k,
        "rerank_top_k": settings.rerank_top_k,
        "rrf_k": settings.rrf_k,
        "hnsw_ef_search": settings.hnsw_ef_search,
        "confidence_threshold_rerank": settings.confidence_threshold_rerank,
        "confidence_threshold_fused": settings.confidence_threshold_fused,
        "citation_similarity_threshold": settings.citation_similarity_threshold,
        "llm_temperature": settings.llm_temperature,
    }


# --------------------------------------------------------------- checkpoint --


def checkpoint_path(run_id: str) -> Path:
    return CHECKPOINT_DIR / f"{run_id}.jsonl"


def load_checkpoint(run_id: str) -> dict[str, CaseResult]:
    """Read already-completed results. Keyed by (case_id, arm) so a resumed
    run does not redo one arm because another finished."""
    path = checkpoint_path(run_id)
    if not path.exists():
        return {}
    done: dict[str, CaseResult] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            result = CaseResult.model_validate_json(line)
        except Exception:  # noqa: BLE001 — a truncated final line after a kill
            logger.warning("skipping unreadable checkpoint line")
            continue
        done[f"{result.case_id}|{result.arm}"] = result
    return done


def append_checkpoint(run_id: str, result: CaseResult) -> None:
    """Append one result, flushed immediately.

    Per case, not per run: the whole point is surviving a process that dies
    without warning when a quota runs out. Buffering would lose exactly the
    work --resume exists to protect.
    """
    path = checkpoint_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(result.model_dump_json() + "\n")
        handle.flush()


# ------------------------------------------------------------------ runner --


class EvalRunner:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        pipeline: ChatPipeline,
        judge: Judge | None,
        settings: Settings,
        concurrency: int,
        retrieval_only: bool,
    ):
        self.pool = pool
        self.pipeline = pipeline
        self.judge = judge
        self.settings = settings
        self.retrieval_only = retrieval_only
        # The rate-limit guard. Every LLM-touching case acquires this, so at
        # most `concurrency` requests are ever in flight.
        self.semaphore = asyncio.Semaphore(concurrency)

    async def run_case(self, resolved: ResolvedCase, arm: str) -> CaseResult:
        case = resolved.case
        result = CaseResult(
            case_id=case.case_id, case_type=case.case_type,
            tenant_id=case.tenant_id, arm=arm,
        )
        result.retrieval.expected_chunk_ids = sorted(resolved.expected_chunk_ids)
        result.retrieval.unresolved = resolved.unresolved

        try:
            if self.retrieval_only:
                await self._retrieval_only(case, resolved, arm, result)
            else:
                async with self.semaphore:
                    await self._full_pipeline(case, resolved, result)
        except Exception as exc:  # noqa: BLE001 — one bad case must not end the run
            logger.exception("case %s failed", case.case_id)
            result.error = f"{type(exc).__name__}: {exc}"
        return result

    async def _retrieval_only(self, case, resolved, arm, result: CaseResult) -> None:
        """Measure retrieval with zero LLM calls.

        Note it uses the RAW query, not a rewritten one — rewriting needs the
        model. For multi-turn cases that understates recall, which is stated
        in the scorecard rather than hidden: the retrieval-only arm answers
        "how good is retrieval given this query string", and comparing arms is
        valid because they all share the handicap.
        """
        mode = "hybrid"
        if arm.startswith("bm25"):
            mode = "bm25"
        elif arm.startswith("vector"):
            mode = "vector"

        scope = TenantScope(self.pool, case.tenant_id)
        retrieval = await self.pipeline.retrieval.retrieve(
            scope, case.query, mode=mode, top_k=self.settings.retrieval_fusion_top_k
        )
        # Metrics are computed over CANDIDATES, not the top-5 results, so
        # recall@20 is measurable at all. Ordering is preserved.
        ordered = [scored.chunk.chunk_id for scored in retrieval.candidates]
        self._score_retrieval(result, ordered, resolved.expected_chunk_ids)
        result.retrieval_ms = retrieval.retrieval_ms
        result.rerank_ms = retrieval.rerank_ms
        result.total_ms = retrieval.total_ms
        result.confidence = retrieval.top_score

    async def _full_pipeline(self, case, resolved, result: CaseResult) -> None:
        response = await self.pipeline.answer(
            ChatRequest(
                tenant_id=case.tenant_id,
                query=case.query,
                messages=[Turn(**turn) for turn in case.history],
            )
        )

        ordered = (
            [scored.chunk.chunk_id for scored in response.retrieval.candidates]
            if response.retrieval else []
        )
        self._score_retrieval(result, ordered, resolved.expected_chunk_ids)

        result.answer = response.answer
        result.action = response.action
        result.abstained = response.is_abstention
        result.confidence = response.confidence
        result.retrieval_ms = response.retrieval_ms
        result.rerank_ms = response.rerank_ms
        result.generation_ms = response.generation_ms
        result.total_ms = response.total_ms
        result.tokens_in = response.tokens_in
        result.tokens_out = response.tokens_out
        result.virtual_cost_usd = response.virtual_cost_usd

        result.must_contain_total = len(case.must_contain)
        result.must_contain_hits = sum(
            1 for literal in case.must_contain if literal.lower() in response.answer.lower()
        )

        result.assertions = run_assertions(case, response)

        # Judging is skipped for abstentions with nothing to judge: there is no
        # answer to check faithfulness of, and the must-abstain assertion has
        # already made the correctness call. Saves a call per abstention, which
        # on a free tier is a meaningful fraction of the budget.
        if self.judge is None:
            result.judge = JudgeScores(skipped=True, skip_reason="judging disabled")
        elif response.is_abstention:
            result.judge = JudgeScores(skipped=True, skip_reason="abstention (see assertions)")
        else:
            context = (
                build_context_block(response.citations, response.retrieval.results)
                if response.retrieval else ""
            )
            async with self.semaphore:
                result.judge = await self.judge.score(
                    question=case.query,
                    context=context,
                    answer=response.answer,
                    reference=case.reference_answer,
                )

    @staticmethod
    def _score_retrieval(result: CaseResult, ordered: list[str], expected: set[str]) -> None:
        metrics = case_metrics(ordered, expected)
        result.retrieval = RetrievalScores(
            expected_chunk_ids=sorted(expected),
            retrieved_chunk_ids=ordered[:20],
            recall_at_5=metrics["recall@5"],
            recall_at_20=metrics["recall@20"],
            precision_at_5=metrics["precision@5"],
            mrr=metrics["mrr"],
            unresolved=result.retrieval.unresolved,
        )


# --------------------------------------------------------------------- CLI --


def build_judge(settings: Settings, model_override: str | None) -> Judge | None:
    """Build a judge on a SEPARATE provider chain from the generator (ADR-020).

    Separate chain, not just a separate model name: the generator's chain has
    Groq's 8b first, and the judge must not silently fall back onto the model
    it is grading. Here the order is reversed so the judge prefers the larger
    model and only falls back to a different provider entirely.
    """
    judge_model = model_override or "llama-3.3-70b-versatile"
    judge_settings = settings.model_copy(update={
        "groq_model": judge_model,
        # Gemini first as fallback, then OpenRouter's 70b. Never the
        # generator's 8b.
        "llm_provider_order": "groq,gemini,openrouter",
    })
    try:
        return Judge(LLMClient(build_providers(judge_settings)), model_name=judge_model)
    except ValueError as exc:
        logger.warning("no judge available (%s) — generation metrics will be skipped", exc)
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--sample", type=int, help="run only the first N cases (smoke test)")
    parser.add_argument("--case-type", help="filter to one case type")
    parser.add_argument("--tenant", help="filter to one tenant")
    parser.add_argument("--resume", help="run_id of a partial run to continue")
    parser.add_argument("--arms", default="hybrid",
                        help="comma-separated: hybrid,bm25,vector (retrieval-only arms)")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="no LLM calls at all — metrics available regardless of quota")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--judge-model", help="override the judge model name")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="max simultaneous LLM calls (free tiers 429 above ~3)")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--tolerance", type=float, default=baseline_module.DEFAULT_TOLERANCE)
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"No golden set at {args.golden}. Run: python scripts/build_golden_set.py")
        return 1

    cases = load_cases(args.golden)
    if args.case_type:
        cases = [c for c in cases if c.case_type == args.case_type]
    if args.tenant:
        cases = [c for c in cases if c.tenant_id == args.tenant]
    if args.sample:
        cases = cases[: args.sample]
    if not cases:
        print("No cases matched the filters.")
        return 1

    settings = get_settings()
    pool = await create_pool(settings.database_url)

    try:
        # Resolve locators BEFORE any expensive work, so a stale golden set
        # fails in seconds rather than after twenty minutes of LLM calls.
        resolved, warnings = await resolve_all(pool, cases)
        for warning in warnings:
            print(f"WARNING  {warning}")
        if warnings:
            print(
                f"\n{len(warnings)} case(s) have unresolved ground truth. This usually means "
                "the corpus was re-ingested with different headings, or ingest has not run.\n"
            )

        encoder = get_encoder(settings.embedding_model_name)
        embeddings = EmbeddingService(pool, encoder)
        llm = build_llm_client_or_none(settings, args.retrieval_only)

        pipeline = ChatPipeline(
            pool=pool,
            retrieval=build_retrieval_service(
                embeddings, settings, with_reranker=not args.no_rerank
            ),
            rewriter=QueryRewriter(llm, enabled=llm is not None and settings.query_rewrite_enabled),
            generator=Generator(llm, abstention_message=settings.abstention_message,
                                temperature=settings.llm_temperature,
                                max_tokens=settings.llm_max_tokens) if llm else None,
            validator=CitationValidator(
                embeddings,
                similarity_threshold=settings.citation_similarity_threshold,
                abstention_message=settings.abstention_message,
            ),
            embeddings=embeddings,
            settings=settings,
        )

        judge = None
        if not args.retrieval_only and not args.no_judge:
            judge = build_judge(settings, args.judge_model)

        run_id = args.resume or f"run-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
        done = load_checkpoint(run_id) if args.resume else {}
        if done:
            print(f"resuming {run_id}: {len(done)} result(s) already recorded")

        arms = [a.strip() for a in args.arms.split(",") if a.strip()]
        if not args.retrieval_only:
            arms = ["hybrid"]  # the full pipeline has one arm; comparison is retrieval-only

        runner = EvalRunner(
            pool=pool, pipeline=pipeline, judge=judge, settings=settings,
            concurrency=args.concurrency, retrieval_only=args.retrieval_only,
        )

        report = RunReport(
            run_id=run_id,
            started_at=dt.datetime.now(dt.timezone.utc),
            git_sha=git_sha(),
            config_snapshot=config_snapshot(settings),
            generator_model=settings.groq_model if llm else "",
            judge_model=judge.model_name if judge else "",
            cases_total=len(cases) * len(arms),
        )

        for arm in arms:
            print(f"\n--- arm: {arm} ---")
            for index, item in enumerate(resolved, start=1):
                key = f"{item.case.case_id}|{arm}"
                if key in done:
                    report.results.append(done[key])
                    continue
                result = await runner.run_case(item, arm)
                report.results.append(result)
                append_checkpoint(run_id, result)
                status = "ERR " if result.error else ("ABST" if result.abstained else "ok  ")
                print(
                    f"  [{index:>3}/{len(resolved)}] {status} {item.case.case_id:<12} "
                    f"r@5={result.retrieval.recall_at_5:.2f} mrr={result.retrieval.mrr:.2f} "
                    f"{result.total_ms}ms"
                )

        report.finished_at = dt.datetime.now(dt.timezone.utc)
        report.cases_run = len(report.results)

        summary = scorecard.build_summary(report)
        print("\n" + scorecard.render(summary, report.results))

        path = scorecard.write_report(report, summary, REPORTS_DIR)
        print(f"\nreport written to {path}")

        if args.write_baseline:
            baseline_module.write_baseline(args.baseline, summary)
            print(f"baseline written to {args.baseline} — commit it")
            return 0

        verdict = baseline_module.compare(
            summary, baseline_module.load_baseline(args.baseline), args.tolerance
        )
        print("\n" + verdict.render())
        return 0 if verdict.passed else 1
    finally:
        await pool.close()


def build_llm_client_or_none(settings: Settings, retrieval_only: bool) -> LLMClient | None:
    if retrieval_only:
        return None
    from app.llm.client import build_llm_client

    try:
        return build_llm_client(settings)
    except ValueError as exc:
        print(f"No LLM configured ({exc}). Falling back to --retrieval-only.")
        return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
