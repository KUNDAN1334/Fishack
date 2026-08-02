"""Tune the confidence gate against the golden set.

    python scripts/tune_thresholds.py                  # sweep the confidence gate
    python scripts/tune_thresholds.py --margin         # sweep the rerank margin

    "Threshold must be configurable and I want a script that helps me TUNE it
     against the golden set."

THE TRADEOFF THIS MEASURES. The confidence gate has exactly one dial and two
ways to be wrong:

  threshold too HIGH  ->  Fishly refuses questions it could have answered.
                          Users experience a broken product. Shows up as a
                          rising escalation rate (Design.md §12).
  threshold too LOW   ->  Fishly answers questions it has no information for.
                          Users experience a confident lie, which is the
                          failure the whole system exists to prevent.

Design.md is explicit that in B2B support the second is more expensive than
the first, so the right operating point is NOT the one that maximizes
accuracy — it is the one that holds false-answers at zero and then recovers as
much coverage as it can. The script reports both error types at every
threshold so that judgement stays yours rather than being buried in an
argmax.

WHY THIS IS FAST. Retrieval runs ONCE per case; the sweep then re-applies the
gate to the recorded scores. The gate is a pure function over a
RetrievalResult (that is why `evaluate_gate` takes no config object), so
sweeping 20 threshold values costs 20 comparisons, not 20 retrieval runs. A
naive implementation would re-retrieve per sweep point and take minutes per
value — which in practice means the sweep never gets run.

NO LLM CALLS. Gate decisions are made before generation by construction, so
tuning needs no quota at all.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.generation.gate import evaluate_gate  # noqa: E402
from app.retrieval.conditional import compute_margin  # noqa: E402
from app.retrieval.service import build_retrieval_service  # noqa: E402
from app.retrieval.tenant_scope import TenantScope  # noqa: E402
from fishnet.models import load_cases  # noqa: E402

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "data" / "golden" / "golden_set.jsonl"


@dataclass
class Observation:
    """One case's retrieval outcome, recorded once and swept many times."""

    case_id: str
    case_type: str
    must_abstain: bool
    top_score: float
    score_kind: str
    fused_scores: list[float]
    has_expected_hit: bool  # did retrieval find a correct chunk at all?


async def collect(pool, cases, settings, no_rerank: bool) -> list[Observation]:
    encoder = get_encoder(settings.embedding_model_name)
    service = build_retrieval_service(
        EmbeddingService(pool, encoder), settings, with_reranker=not no_rerank
    )

    from fishnet.resolver import resolve_all

    resolved, _ = await resolve_all(pool, cases)
    observations: list[Observation] = []

    for index, item in enumerate(resolved, start=1):
        scope = TenantScope(pool, item.case.tenant_id)
        retrieval = await service.retrieve(scope, item.case.query, mode="hybrid")

        gate = evaluate_gate(retrieval, threshold_rerank=0.0, threshold_fused=0.0)
        retrieved = {s.chunk.chunk_id for s in retrieval.results}

        observations.append(
            Observation(
                case_id=item.case.case_id,
                case_type=item.case.case_type,
                must_abstain=item.case.must_abstain,
                top_score=gate.top_score,
                score_kind=gate.score_kind,
                fused_scores=[c.fused_score for c in retrieval.candidates],
                has_expected_hit=bool(retrieved & item.expected_chunk_ids),
            )
        )
        if index % 10 == 0:
            print(f"  ...{index}/{len(resolved)}")
    return observations


def sweep_confidence(observations: list[Observation], kind: str) -> None:
    """Sweep the gate threshold for one score scale.

    Scales are swept separately (ADR-015): reranker scores live in 0-1, RRF
    scores around 0.02, so one sweep range cannot serve both.
    """
    relevant = [o for o in observations if o.score_kind == kind]
    if not relevant:
        print(f"\nno cases scored on the '{kind}' scale — skipping")
        return

    values = sorted(o.top_score for o in relevant)
    lo, hi = values[0], values[-1]
    steps = [lo + (hi - lo) * i / 20 for i in range(21)] if hi > lo else [lo]

    should_abstain = [o for o in relevant if o.must_abstain]
    should_answer = [o for o in relevant if not o.must_abstain]

    print(f"\n{'=' * 92}")
    print(f"CONFIDENCE GATE SWEEP — '{kind}' scale, {len(relevant)} cases "
          f"({len(should_abstain)} must abstain, {len(should_answer)} should be answerable)")
    print("=" * 92)
    print(f"{'threshold':>10} {'correct abstain':>16} {'MISSED abstain':>16} "
          f"{'wrongly refused':>16} {'answered ok':>13}")
    print("-" * 92)

    best = None
    for threshold in steps:
        # Correct: an out-of-scope case whose score fell below the bar.
        correct_abstain = sum(1 for o in should_abstain if o.top_score < threshold)
        # The expensive error: an out-of-scope case we would have ANSWERED.
        missed_abstain = len(should_abstain) - correct_abstain
        # The other error: an answerable case refused.
        wrongly_refused = sum(1 for o in should_answer if o.top_score < threshold)
        answered_ok = len(should_answer) - wrongly_refused

        marker = ""
        # The operating point Design.md implies: zero missed abstentions
        # first, then maximum coverage. Not the accuracy argmax.
        if missed_abstain == 0 and (best is None or answered_ok > best[1]):
            best = (threshold, answered_ok)
            marker = "  <- zero false answers, best coverage so far"

        print(f"{threshold:>10.4f} {correct_abstain:>16} {missed_abstain:>16} "
              f"{wrongly_refused:>16} {answered_ok:>13}{marker}")

    print("-" * 92)
    if best:
        print(f"RECOMMENDED {kind} threshold: {best[0]:.4f}")
        print(f"  zero out-of-scope questions answered, {best[1]}/{len(should_answer)} "
              f"answerable cases still answered.")
    else:
        print("No threshold eliminates false answers — retrieval is scoring out-of-scope")
        print("queries as highly as real ones. That is a RETRIEVAL problem, not a")
        print("threshold problem, and no gate setting will fix it.")
    print("=" * 92)


def sweep_margin(observations: list[Observation], window: int) -> None:
    """Sweep the conditional-rerank ambiguity margin (ADR-014).

    Reports the distribution, because the open question recorded in ADR-014 is
    not "what threshold" but "does this signal have enough dynamic range to be
    thresholded at all". A sweep that shows every case inside a 0.02 band
    answers that question in the negative, which is a finding.
    """
    margins = [
        m for o in observations
        if (m := compute_margin(o.fused_scores, window)) is not None
    ]
    if not margins:
        print("\nno margins computable")
        return

    margins.sort()
    print(f"\n{'=' * 92}")
    print(f"RERANK MARGIN DISTRIBUTION — {len(margins)} cases, window={window}")
    print("=" * 92)
    for label, index in (("min", 0), ("p25", len(margins) // 4), ("median", len(margins) // 2),
                         ("p75", 3 * len(margins) // 4), ("max", -1)):
        print(f"  {label:<8} {margins[index]:.4f}")

    print(f"\n{'threshold':>10} {'would SKIP rerank':>20} {'would rerank':>15}")
    print("-" * 92)
    for threshold in [0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30]:
        skip = sum(1 for m in margins if m >= threshold)
        print(f"{threshold:>10.2f} {skip:>20} {len(margins) - skip:>15}")
    print("-" * 92)
    print("A threshold that skips 0 or all cases is not a control — it is a constant.")
    print("=" * 92)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--sample", type=int)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--margin", action="store_true",
                        help="sweep the conditional-rerank margin instead of the gate")
    args = parser.parse_args()

    settings = get_settings()
    cases = load_cases(args.golden)
    if args.sample:
        cases = cases[: args.sample]

    pool = await create_pool(settings.database_url)
    try:
        print(f"retrieving {len(cases)} cases once (no LLM calls)...")
        observations = await collect(pool, cases, settings, args.no_rerank)

        if args.margin:
            sweep_margin(observations, settings.rerank_ambiguity_window)
        else:
            sweep_confidence(observations, "rerank")
            sweep_confidence(observations, "fused")
            print(
                f"\nCurrent config: rerank={settings.confidence_threshold_rerank} "
                f"fused={settings.confidence_threshold_fused}"
            )
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
