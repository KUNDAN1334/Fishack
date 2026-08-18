"""Turn feedback into work (Design.md §10).

    python scripts/triage_feedback.py                    # triage report
    python scripts/triage_feedback.py --days 30
    python scripts/triage_feedback.py --golden-candidates # 👍 -> eval cases

Design.md §10 asks for two things, and they are opposite directions of the
same flywheel:

  👎  ->  a triage report classifying each failure as retrieval, generation or
          stale data, so you know which component to open
  👍  ->  golden-set candidates, so today's good answers become tomorrow's
          regression tests

The classification logic lives in `app/feedback/triage.py` as pure functions —
this script only queries and prints. That separation means the classifier can
be unit-tested against hand-written traces with no database, and the same
logic could later serve a dashboard without being lifted out of a CLI.

WHY 👍 BECOMES A *CANDIDATE*, NOT A CASE. Positive feedback means the user was
satisfied, which is not the same as the answer being correct — users thumbs-up
confident-sounding answers. So the script writes a file for review rather than
appending to the golden set. Auto-promoting production output into ground
truth would let the system grade itself, which is precisely the correlated-
failure problem from ADR-020 wearing a different hat.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.feedback.triage import Triage, classify, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "golden" / "candidates.jsonl"
WIDTH = 96

# Joins feedback to its trace and, crucially, checks whether any CITED chunk
# was flagged at ingestion as contradicted by a newer changelog entry
# (ADR-009). That single boolean is what separates "the model got it wrong"
# from "the corpus was out of date", and it is only knowable by looking at the
# chunk metadata — which is why it is computed in SQL rather than guessed.
_FEEDBACK_SQL = """
SELECT f.id            AS feedback_id,
       f.rating,
       f.comment,
       f.created_at,
       t.id,
       t.tenant_id,
       t.query,
       t.rewritten_query,
       t.answer,
       t.action,
       t.confidence,
       t.cache_status,
       t.citation_report,
       t.retrieved_chunk_ids,
       EXISTS (
           SELECT 1 FROM chunks c
            WHERE c.id = ANY(t.retrieved_chunk_ids)
              AND c.metadata ? 'conflicts_with_entry'
       )               AS contested_cited
  FROM feedback f
  JOIN traces t ON t.id = f.trace_id
 WHERE f.created_at >= now() - ($1 || ' days')::interval
   AND ($2::text IS NULL OR f.tenant_id = $2)
   AND f.rating = $3
 ORDER BY f.created_at DESC
"""


def _row_to_trace(row) -> dict:
    """asyncpg gives JSONB back as a string unless a codec is registered."""
    report = row["citation_report"]
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except (TypeError, ValueError):
            report = {}
    return {
        "id": row["id"],
        "query": row["rewritten_query"] or row["query"],
        "action": row["action"],
        "confidence": row["confidence"],
        "cache_status": row["cache_status"],
        "citation_report": report or {},
        "retrieved_chunk_ids": row["retrieved_chunk_ids"] or [],
        "contested_cited": row["contested_cited"],
    }


async def cmd_triage(args, pool) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FEEDBACK_SQL, str(args.days), args.tenant, -1)

    if not rows:
        print(f"No thumbs-down feedback in the last {args.days} days.")
        print("Give some via POST /feedback, or run the chat playground first.")
        return 0

    triaged: list[Triage] = [classify(_row_to_trace(row)) for row in rows]
    counts = summarize(triaged)

    print("=" * WIDTH)
    print(f"FEEDBACK TRIAGE — {len(triaged)} thumbs-down, last {args.days} days"
          + (f", tenant {args.tenant}" if args.tenant else ""))
    print("=" * WIDTH)

    # Counts first. This is the number that decides what to work on next, and
    # burying it under 40 individual cases is how a report stops being read.
    print("\nBY CATEGORY")
    print("-" * WIDTH)
    for category, count in counts.items():
        share = count / len(triaged)
        bar = "#" * int(share * 40)
        print(f"  {category:<12} {count:>4}  {share:>5.0%}  {bar}")

    print("\n  what each category means you should fix:")
    for category in counts:
        print(f"    {category:<12} {Triage(trace_id='', category=category, reason='').suggested_fix}")

    print("\n\nCASES")
    print("-" * WIDTH)
    for item, row in zip(triaged, rows):
        print(f"\n  [{item.category}] {item.query[:72]}")
        print(f"    why      : {item.reason}")
        print(f"    trace    : {item.trace_id}  confidence={item.confidence:.3f}")
        if row["comment"]:
            print(f"    user said: {row['comment'][:80]}")
        if args.verbose:
            print(f"    answer   : {(row['answer'] or '')[:160]}")
            print(f"    signals  : {item.signals}")

    print("\n" + "=" * WIDTH)
    top = next(iter(counts), None)
    if top:
        print(f"BIGGEST BUCKET: {top} ({counts[top]}/{len(triaged)})")
        print(f"  -> {FIXES_HINT.get(top, 'investigate')}")
    print("=" * WIDTH)
    return 0


FIXES_HINT = {
    "retrieval": "run `make eval-retrieval` and look at recall per case type",
    "generation": "run `chat_playground.py --show-prompt` on a failing query",
    "stale_data": "re-ingest, and check the conflict rule in prompts.py",
    "cache": "consider raising semantic_cache_threshold, or check invalidation",
    "unclear": "read the answers by hand — the trace is not enough",
}


async def cmd_candidates(args, pool) -> int:
    """Turn 👍 answers into golden-set candidates for review."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FEEDBACK_SQL, str(args.days), args.tenant, 1)

    if not rows:
        print(f"No thumbs-up feedback in the last {args.days} days.")
        return 0

    written = 0
    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            trace = _row_to_trace(row)
            report = trace["citation_report"]

            # Only well-grounded answers become candidates. A satisfied user is
            # not evidence of correctness — people thumbs-up fluent answers —
            # so we require the citation validator to agree before promoting
            # anything toward ground truth.
            grounding = report.get("grounding_rate")
            if grounding is not None and grounding < 0.8:
                continue
            if report.get("has_fabricated_citations"):
                continue
            if row["action"] != "answered":
                continue

            handle.write(json.dumps({
                "_source": "positive_feedback",
                "_trace_id": str(row["id"]),
                "_needs_review": True,
                "case_id": f"fb-{str(row['id'])[:8]}",
                "case_type": "normal",
                "tenant_id": row["tenant_id"],
                "query": trace["query"],
                "reference_answer": row["answer"],
                # Chunk ids, deliberately NOT converted into locators. A human
                # must decide which source is genuinely the ground truth for
                # this question — ADR-019 exists because chunk ids are not
                # stable, and auto-generating locators from a single good
                # answer would bake one retrieval run into permanent truth.
                "_retrieved_chunk_ids": [str(c) for c in trace["retrieved_chunk_ids"]],
                "expected_sources": [],
            }, ensure_ascii=False) + "\n")
            written += 1

    print(f"wrote {written} candidate(s) from {len(rows)} thumbs-up to {CANDIDATES}")
    print("\nThese are CANDIDATES, not cases. For each one:")
    print("  1. check the question is one a customer would really ask")
    print("  2. replace _retrieved_chunk_ids with real `expected_sources` locators")
    print("  3. trim the reference answer to what a good answer must contain")
    print("  4. move the line into data/golden/golden_set.jsonl")
    print("\nA golden set that grows automatically stops being ground truth.")
    return 0


async def cmd_summary(args, pool) -> int:
    """One-line health check across both ratings."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT count(*) FILTER (WHERE rating = 1)  AS up,
                   count(*) FILTER (WHERE rating = -1) AS down,
                   count(DISTINCT tenant_id)           AS tenants
              FROM feedback
             WHERE created_at >= now() - ($1 || ' days')::interval
            """,
            str(args.days),
        )
    total = (row["up"] or 0) + (row["down"] or 0)
    print(f"last {args.days} days: {row['up']} up, {row['down']} down "
          f"across {row['tenants']} tenant(s)")
    if total:
        print(f"satisfaction: {(row['up'] or 0) / total:.0%}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--tenant")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--golden-candidates", action="store_true",
                        help="write thumbs-up answers as golden-set candidates")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    pool = await create_pool(get_settings().database_url)
    try:
        if args.summary:
            return await cmd_summary(args, pool)
        if args.golden_candidates:
            return await cmd_candidates(args, pool)
        return await cmd_triage(args, pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
