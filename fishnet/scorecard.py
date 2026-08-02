"""Turning a run into a table and a JSON report (Design.md §12).

    "one command prints a table + writes a timestamped JSON report so I can
     diff runs"

Two audiences, two formats. The table is for a human deciding whether a change
helped; the JSON is for the next run's baseline comparison and for diffing.
They are produced from the same aggregation so they can never disagree.

What the table shows and why, in order of what you look at first:

  1. HARD ASSERTIONS, at the top, before any quality number. If a
     must-abstain case answered, no amount of good recall makes the run
     acceptable, and burying that under three tables of metrics is how it gets
     missed.
  2. RETRIEVAL, per case type. The per-type split is the whole value: an
     aggregate hides that identifier queries are failing.
  3. GENERATION, separately from retrieval, because they are independent
     failure points (Design.md §12).
  4. COST AND LATENCY, because Design.md §9 makes both hard constraints.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from fishnet.metrics import aggregate, summarize
from fishnet.models import CaseResult, RunReport

# Metric column order, fixed so two scorecards line up visually when read side
# by side in a terminal.
RETRIEVAL_METRICS = ["recall@5", "recall@20", "precision@5", "mrr", "hit@5"]
GENERATION_METRICS = ["faithfulness", "citation_accuracy", "answer_relevance"]

WIDTH = 88


def retrieval_summary(results: list[CaseResult]) -> dict[str, dict[str, float]]:
    per_case = [
        (
            result.case_type,
            {
                "recall@5": result.retrieval.recall_at_5,
                "recall@20": result.retrieval.recall_at_20,
                "precision@5": result.retrieval.precision_at_5,
                "mrr": result.retrieval.mrr,
                "hit@5": 1.0 if result.retrieval.recall_at_5 > 0 else 0.0,
            },
        )
        for result in results
    ]
    return summarize(per_case)


def generation_summary(results: list[CaseResult]) -> dict[str, float]:
    """Averaged over cases the judge actually scored.

    Skipped judgements (quota exhausted, unparseable output) are EXCLUDED
    rather than counted as 0.0. Averaging "not measured" with "measured badly"
    produces a number that means neither, and on a free tier the skip rate can
    be high enough to dominate. `judged` reports the denominator so a scorecard
    computed over 12 of 60 cases cannot be mistaken for one computed over all.
    """
    scored = [result.judge for result in results if not result.judge.skipped]
    summary: dict[str, float] = {"judged": float(len(scored)), "skipped": float(
        sum(1 for result in results if result.judge.skipped)
    )}
    for metric in GENERATION_METRICS:
        values = [
            getattr(judge, metric) for judge in scored if getattr(judge, metric) is not None
        ]
        summary[metric] = aggregate(values)
    return summary


def assertion_summary(results: list[CaseResult]) -> dict[str, dict[str, int]]:
    """Per-assertion pass/fail counts. Failures are listed individually in the
    table — a count alone tells you something broke but not what."""
    summary: dict[str, dict[str, int]] = {}
    for result in results:
        for assertion in result.assertions:
            bucket = summary.setdefault(assertion.name, {"passed": 0, "failed": 0})
            bucket["passed" if assertion.passed else "failed"] += 1
    return summary


def cost_summary(results: list[CaseResult]) -> dict[str, float]:
    """Design.md §9 and §12 both make cost per query a first-class metric.

    p95 by nearest-rank on a sorted list — not interpolated. With 60 cases,
    interpolation invents precision the sample size does not support.
    """
    totals = sorted(result.total_ms for result in results) or [0]
    p95_index = max(0, int(len(totals) * 0.95) - 1)
    answered = [r for r in results if not r.abstained]
    return {
        "total_virtual_cost_usd": sum(r.virtual_cost_usd for r in results),
        "cost_per_query_usd": aggregate([r.virtual_cost_usd for r in results]),
        "p50_total_ms": totals[len(totals) // 2],
        "p95_total_ms": totals[p95_index],
        "mean_retrieval_ms": aggregate([float(r.retrieval_ms) for r in results]),
        "mean_rerank_ms": aggregate([float(r.rerank_ms) for r in results]),
        "mean_generation_ms": aggregate([float(r.generation_ms) for r in results]),
        "abstention_rate": aggregate([float(r.abstained) for r in results]),
        "answered": float(len(answered)),
    }


def build_summary(report: RunReport) -> dict:
    """The whole scorecard as plain data — what gets written to JSON, compared
    against a baseline, and rendered as a table."""
    return {
        "run_id": report.run_id,
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "duration_seconds": report.duration_seconds,
        "git_sha": report.git_sha,
        "generator_model": report.generator_model,
        "judge_model": report.judge_model,
        "cases_total": report.cases_total,
        "cases_run": report.cases_run,
        "config": report.config_snapshot,
        "retrieval": retrieval_summary(report.results),
        "generation": generation_summary(report.results),
        "assertions": assertion_summary(report.results),
        "cost": cost_summary(report.results),
    }


# ------------------------------------------------------------- rendering --


def _row(label: str, values: dict[str, float], columns: list[str]) -> str:
    cells = "".join(f"{values.get(column, 0.0):>13.3f}" for column in columns)
    return f"  {label:<22}{cells}"


def render(summary: dict, results: list[CaseResult]) -> str:
    """The printed scorecard."""
    lines: list[str] = []
    add = lines.append

    add("=" * WIDTH)
    add(f"FISHNET SCORECARD  {summary['run_id']}")
    add(
        f"  generator={summary['generator_model'] or '-'}  "
        f"judge={summary['judge_model'] or '-'}"
    )
    add(
        f"  cases={summary['cases_run']}/{summary['cases_total']}  "
        f"duration={summary['duration_seconds']:.0f}s  git={summary['git_sha'] or '-'}"
    )
    add("=" * WIDTH)

    # --- 1. hard assertions FIRST -----------------------------------------
    add("\nHARD ASSERTIONS (correctness — any failure fails the build)")
    add("-" * WIDTH)
    assertions = summary["assertions"]
    if not assertions:
        add("  (none applicable)")
    for name, counts in sorted(assertions.items()):
        total = counts["passed"] + counts["failed"]
        mark = "PASS" if counts["failed"] == 0 else "FAIL"
        add(f"  {mark}  {name:<28} {counts['passed']}/{total}")

    failures = [
        (result.case_id, assertion)
        for result in results
        for assertion in result.assertions
        if not assertion.passed
    ]
    for case_id, assertion in failures:
        add(f"        {case_id}: {assertion.name} — {assertion.detail[:70]}")

    # --- 2. retrieval, per case type --------------------------------------
    add("\nRETRIEVAL")
    add("-" * WIDTH)
    add("  " + " " * 22 + "".join(f"{m:>13}" for m in RETRIEVAL_METRICS))
    retrieval = summary["retrieval"]
    if "overall" in retrieval:
        add(_row("overall", retrieval["overall"], RETRIEVAL_METRICS))
    for case_type in sorted(k for k in retrieval if k != "overall"):
        add(_row(f"  {case_type}", retrieval[case_type], RETRIEVAL_METRICS))

    # --- 3. generation, measured separately -------------------------------
    add("\nGENERATION (LLM-as-judge)")
    add("-" * WIDTH)
    generation = summary["generation"]
    add(
        f"  judged {generation['judged']:.0f} cases, "
        f"skipped {generation['skipped']:.0f} (quota / parse failures)"
    )
    for metric in GENERATION_METRICS:
        add(f"  {metric:<22}{generation.get(metric, 0.0):>13.3f}")

    # --- 4. cost and latency ----------------------------------------------
    add("\nCOST & LATENCY")
    add("-" * WIDTH)
    cost = summary["cost"]
    add(f"  cost per query        ${cost['cost_per_query_usd']:.6f} (virtual)")
    add(f"  total virtual cost    ${cost['total_virtual_cost_usd']:.4f}")
    add(f"  latency p50 / p95     {cost['p50_total_ms']:.0f}ms / {cost['p95_total_ms']:.0f}ms")
    add(
        f"  mean stage ms         retrieval={cost['mean_retrieval_ms']:.0f} "
        f"rerank={cost['mean_rerank_ms']:.0f} generation={cost['mean_generation_ms']:.0f}"
    )
    add(f"  abstention rate       {cost['abstention_rate']:.1%}")
    add("=" * WIDTH)
    return "\n".join(lines)


def write_report(report: RunReport, summary: dict, output_dir: Path) -> Path:
    """Write the timestamped JSON report.

    Per-case results are included alongside the aggregates. Aggregates tell you
    a run got worse; only the per-case detail tells you WHICH cases, and
    re-running to find out costs another full quota budget.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"fishnet_{stamp}.json"
    payload = {
        "summary": summary,
        "cases": [result.model_dump(mode="json") for result in report.results],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
