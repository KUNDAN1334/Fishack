"""Regression detection against a committed baseline (ADR-022).

    "CI fails if any metric drops >X% vs the committed baseline"

Two tolerances, because there are two kinds of number in this harness.

QUALITY METRICS (recall@5, MRR, faithfulness, citation accuracy) move
continuously and are genuinely noisy — LLM-judge scores especially, since the
same answer can score differently on consecutive judgements. A 5% relative
tolerance is wide enough to absorb that noise and narrow enough to catch a
real regression.

HARD ASSERTIONS (must-abstain, must-not-leak, no fabricated citations) get
ZERO tolerance. There is no acceptable rate of cross-tenant leakage. Applying
a percentage band to a correctness check is how a security bug gets absorbed
by a quality budget.

Why compare against a COMMITTED baseline rather than the previous run: a
baseline in git is a deliberate act. Someone looked at a scorecard, decided it
represented the intended behaviour, and committed it — with a diff showing
exactly which numbers changed. Auto-updating from the last run would let
quality erode one tolerated 4% drop at a time, each individually acceptable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fishnet.metrics import relative_delta

# Relative drop tolerated on a quality metric before CI fails.
DEFAULT_TOLERANCE = 0.05

# The metrics the gate actually guards. Deliberately short: gating on
# everything means gating on nothing, because someone will start ignoring the
# output. These are the numbers that describe whether the system works.
GUARDED_RETRIEVAL = ["recall@5", "recall@20", "mrr"]
GUARDED_GENERATION = ["faithfulness", "citation_accuracy"]


@dataclass
class MetricComparison:
    name: str
    baseline: float
    current: float
    delta: float          # relative
    regressed: bool

    def render(self) -> str:
        arrow = "v" if self.delta < 0 else ("^" if self.delta > 0 else "=")
        mark = "FAIL" if self.regressed else "ok  "
        return (
            f"  {mark} {self.name:<34} {self.baseline:>7.3f} -> {self.current:>7.3f}  "
            f"{arrow}{abs(self.delta):>6.1%}"
        )


@dataclass
class BaselineVerdict:
    comparisons: list[MetricComparison]
    assertion_failures: list[str]
    missing_baseline: bool = False

    @property
    def passed(self) -> bool:
        if self.missing_baseline:
            # No baseline yet is not a failure — it is the first run. It must
            # not block CI on a fresh clone, or nobody can ever create one.
            return True
        return not self.assertion_failures and not any(c.regressed for c in self.comparisons)

    def render(self) -> str:
        lines = ["=" * 88, "BASELINE COMPARISON", "=" * 88]
        if self.missing_baseline:
            lines.append("  no committed baseline — run with --write-baseline to create one")
            lines.append("=" * 88)
            return "\n".join(lines)

        # Assertions first: a correctness failure outranks every quality number.
        if self.assertion_failures:
            lines.append("\n  HARD ASSERTION FAILURES (zero tolerance):")
            lines.extend(f"    FAIL {failure}" for failure in self.assertion_failures)

        lines.append("")
        lines.extend(comparison.render() for comparison in self.comparisons)
        lines.append("")
        lines.append("  RESULT: " + ("PASS" if self.passed else "FAIL"))
        lines.append("=" * 88)
        return "\n".join(lines)


def load_baseline(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, summary: dict) -> None:
    """Commit-worthy baseline.

    Per-case results are deliberately EXCLUDED — only aggregates and the
    config that produced them. A baseline carrying 60 answers would produce an
    unreadable diff on every commit, and the answers are not what we are
    gating on.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = {
        "generator_model": summary.get("generator_model"),
        "judge_model": summary.get("judge_model"),
        "cases_total": summary.get("cases_total"),
        "config": summary.get("config", {}),
        "retrieval": summary.get("retrieval", {}),
        "generation": summary.get("generation", {}),
        "assertions": summary.get("assertions", {}),
        "cost": summary.get("cost", {}),
    }
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compare(summary: dict, baseline: dict | None, tolerance: float = DEFAULT_TOLERANCE) -> BaselineVerdict:
    """Compare a run against the committed baseline."""
    if baseline is None:
        return BaselineVerdict(comparisons=[], assertion_failures=[], missing_baseline=True)

    comparisons: list[MetricComparison] = []

    def add(name: str, current: float, previous: float) -> None:
        delta = relative_delta(current, previous)
        comparisons.append(
            MetricComparison(
                name=name, baseline=previous, current=current, delta=delta,
                # Only DROPS regress. An improvement is never a failure, which
                # sounds obvious until you write `abs(delta) > tolerance` and
                # start failing builds for getting better.
                regressed=delta < -tolerance,
            )
        )

    current_retrieval = summary.get("retrieval", {}).get("overall", {})
    baseline_retrieval = baseline.get("retrieval", {}).get("overall", {})
    for metric in GUARDED_RETRIEVAL:
        if metric in baseline_retrieval:
            add(f"retrieval.{metric}", current_retrieval.get(metric, 0.0), baseline_retrieval[metric])

    current_generation = summary.get("generation", {})
    baseline_generation = baseline.get("generation", {})
    for metric in GUARDED_GENERATION:
        if metric in baseline_generation:
            # Skip when the judge barely ran this time. Comparing a score over
            # 8 cases against a baseline over 60 is not a comparison, and on a
            # free tier a quota-limited run is common enough that failing on it
            # would train people to ignore the gate.
            if current_generation.get("judged", 0) < max(3, baseline.get("cases_total", 0) * 0.25):
                continue
            add(f"generation.{metric}", current_generation.get(metric, 0.0), baseline_generation[metric])

    # Hard assertions: any failure at all, regardless of the baseline.
    assertion_failures = [
        f"{name}: {counts['failed']} failing"
        for name, counts in sorted(summary.get("assertions", {}).items())
        if counts.get("failed", 0) > 0
    ]

    return BaselineVerdict(comparisons=comparisons, assertion_failures=assertion_failures)
