"""Generate the golden set from the corpus spec (ADR-021).

    python scripts/build_golden_set.py            # write data/golden/golden_set.jsonl
    python scripts/build_golden_set.py --stats    # case counts per type, no write

The golden set is DERIVED, not written by hand or by an LLM, and that follows
directly from ADR-008. `data/generation/spec.py` declares every document,
error code, version, date and planted conflict in Python. So we already know —
with certainty, not inference — which source answers "how many webhook retry
attempts?" and which changelog entry contradicts it.

Why not hand-written: 60 cases is a day of work, and every re-ingestion risks
invalidating ground truth someone guessed at.

Why not LLM-generated: an LLM asked to write eval cases from a corpus produces
plausible questions with plausible expected sources — and "plausible" is
exactly the failure mode an eval harness exists to detect. Ground truth that
was itself generated cannot be trusted to grade generation.

The output is committed and MEANT TO BE EDITED. This script produces a
starting set of correct-by-construction cases; a human then fixes awkward
phrasing, adds cases the spec cannot express, and deletes ones that turn out
to be ambiguous. Re-running overwrites, so edit after generating, or pass
--output to a different file and merge.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.generation.spec import (  # noqa: E402
    ALL_DOCS,
    CHANGELOG,
    TICKETS,
    docs_for_tenant,
)
from fishnet.models import GoldenCase, SourceLocator, save_cases  # noqa: E402

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "golden" / "golden_set.jsonl"

TENANTS = ("acme", "globex")


def doc_locator(slug: str, heading: str | None = None) -> SourceLocator:
    return SourceLocator(source_type="docs", slug=slug, heading=heading)


# ---------------------------------------------------------------------------
# 1. NORMAL — a question answerable from one documented section.
# ---------------------------------------------------------------------------
# Handpicked rather than generated across all 60 docs: a question needs to be
# something a customer would actually type, and "tell me about Section 3 of
# the SSO Setup page" is not that. These are drawn from sections whose subject
# is a real support question.

NORMAL_SEEDS: list[tuple[str, str, str, str, list[str]]] = [
    # (doc slug, heading, query, reference answer, must_contain)
    ("webhooks-security", "Signature Verification",
     "How do I verify that a webhook actually came from Flowlytics?",
     "Each webhook payload carries an HMAC-SHA256 signature in the X-Flowlytics-Signature "
     "header; recompute it with your signing secret and compare.",
     ["signature"]),
    ("api-authentication", "Key Rotation",
     "How do I rotate an API key without downtime?",
     "Create the new key, deploy it alongside the old one, then revoke the old key once "
     "traffic has moved — the rotation procedure supports both keys being valid at once.",
     []),
    ("api-rate-limits", "Rate Limit Headers",
     "Which headers tell me how much of my rate limit is left?",
     "Responses carry X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset.",
     ["X-RateLimit-Remaining"]),
    ("billing-invoices", None,
     "When are invoices generated?",
     "Invoices are generated at the end of each billing cycle.",
     []),
    ("data-retention", None,
     "How long is my event data retained?",
     "Retention depends on plan; the Data Retention page states the per-plan windows.",
     []),
    ("sso-setup", None,
     "How do I set up SAML single sign-on?",
     "Configure the identity provider with Flowlytics' ACS URL and entity ID, then map "
     "the required attributes.",
     []),
    ("data-ingestion-api", "Batch Limits",
     "What is the maximum number of events I can send in one batch?",
     "Ingestion batches may contain up to 500 events.",
     ["500"]),
    ("integrations-snowflake", None,
     "How do I connect Flowlytics to Snowflake?",
     "Configure the Snowflake integration with the warehouse, database and credentials; "
     "the integration is generally available since v2.3.",
     []),
]


def build_normal() -> list[GoldenCase]:
    cases = []
    for index, (slug, heading, query, reference, must_contain) in enumerate(NORMAL_SEEDS, start=1):
        for tenant in TENANTS:
            # Only shared docs get both tenants; a tenant-specific doc would
            # resolve to nothing for the other one.
            if slug not in {d.slug for d in docs_for_tenant(tenant)}:
                continue
            cases.append(
                GoldenCase(
                    case_id=f"norm-{index:02d}-{tenant[:3]}",
                    case_type="normal",
                    tenant_id=tenant,
                    query=query,
                    expected_sources=[doc_locator(slug, heading)],
                    reference_answer=reference,
                    must_contain=must_contain,
                    notes=f"documented in {slug}",
                )
            )
    return cases


# ---------------------------------------------------------------------------
# 2. EXACT_IDENTIFIER — the case hybrid retrieval exists for (Design.md §5).
# ---------------------------------------------------------------------------
# Generated from tickets that carry an error_code. These are the queries where
# pure vector search drifts to "connection error" documentation and BM25's
# phrase matching earns its place.


def build_exact_identifier() -> list[GoldenCase]:
    cases = []
    seen: set[tuple[str, str]] = set()
    for ticket in TICKETS:
        if not ticket.error_code:
            continue
        key = (ticket.tenant, ticket.error_code)
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            GoldenCase(
                case_id=f"ident-{ticket.ticket_id.lower()}",
                case_type="exact_identifier",
                tenant_id=ticket.tenant,
                query=f"What causes {ticket.error_code}?",
                expected_sources=[
                    SourceLocator(source_type="ticket", ticket_id=ticket.ticket_id)
                ],
                reference_answer=ticket.answer_hint,
                # The literal must survive into the answer. This is the cheap
                # deterministic check the LLM judge is worst at: a fluent
                # answer that never names the code it was asked about.
                must_contain=[ticket.error_code],
                notes=f"error code from ticket {ticket.ticket_id}",
            )
        )
    return cases


# ---------------------------------------------------------------------------
# 3. STALE_CONFLICT — the planted contradictions (ADR-009, Design.md §11a).
# ---------------------------------------------------------------------------
# Every changelog entry with `conflicts_with` is a case by construction: the
# doc says one thing, the newer entry says another, both stay retrievable, and
# a correct answer must prefer the newer AND say the older disagrees.

# entry_id -> (query, reference answer, must_contain, contested heading)
#
# The HEADING matters more than it looks, and its absence was a real bug.
#
# A docs locator with no heading resolves to EVERY chunk of the page. The
# webhooks-overview page is ~7 chunks, so a case expecting "the changelog plus
# that whole page" has an expected set of ~8 — and recall@5 is then
# arithmetically capped at 5/8 = 0.63 no matter how perfect retrieval is. The
# first stale_conflict numbers (0.43, 0.46) looked like a system failure and
# were largely a measurement artifact.
#
# Naming the contested section makes the expected set what the case actually
# means: the changelog entry, and the one passage it contradicts.
CONFLICT_QUERIES: dict[str, tuple[str, str, list[str], str]] = {
    "CL-2026-0610-01": (
        "How many times will a failed webhook be retried?",
        "Up to 5 attempts as of v2.4 (2026-06-10). The Webhooks Overview page still says 3; "
        "it predates the change and is out of date.",
        ["5"],
        "Retry Logic",
    ),
    "CL-2026-0610-02": (
        "How long until my events show up in the dashboard?",
        "Within 5 minutes as of v2.4. The Data Sync and Latency page still says 15 minutes "
        "and is out of date.",
        ["5"],
        "Expected Latency",
    ),
    "CL-2026-0610-04": (
        "What is the overage rate per 1,000 events?",
        "$0.08 per 1,000 events as of v2.4, reduced from $0.10. The usage metering page "
        "still quotes the older rate.",
        ["0.08"],
        "Overage",
    ),
    "CL-2026-0610-05": (
        "How long can a query run before it times out?",
        "60 seconds as of v2.4, raised from 30. The Query Engine page still states the "
        "older 30 second limit.",
        ["60"],
        "Timeout",
    ),
}


def build_stale_conflict() -> list[GoldenCase]:
    cases = []
    for entry in CHANGELOG:
        if not entry.conflicts_with or entry.entry_id not in CONFLICT_QUERIES:
            continue
        query, reference, must_contain, heading = CONFLICT_QUERIES[entry.entry_id]
        for tenant in TENANTS:
            if entry.tenant and entry.tenant != tenant:
                continue
            cases.append(
                GoldenCase(
                    case_id=f"stale-{entry.entry_id[-2:]}-{tenant[:3]}",
                    case_type="stale_conflict",
                    tenant_id=tenant,
                    query=query,
                    # BOTH sources are expected. Retrieving only the changelog
                    # would produce a correct number with no discrepancy
                    # flagged; retrieving only the doc produces a stale answer.
                    # The conflict rule needs both in context to fire at all.
                    expected_sources=[
                        SourceLocator(source_type="changelog", entry_id=entry.entry_id),
                        # Narrowed to the contested SECTION, not the whole
                        # page — see the note on CONFLICT_QUERIES.
                        doc_locator(entry.conflicts_with, heading),
                    ],
                    reference_answer=reference,
                    must_contain=must_contain,
                    notes=f"planted conflict: {entry.entry_id} vs {entry.conflicts_with}",
                )
            )
    return cases


# ---------------------------------------------------------------------------
# 4. MULTI_TURN — follow-ups that only resolve with history (Design.md §2.2).
# ---------------------------------------------------------------------------
# The query alone is deliberately unanswerable. If the harness scores these
# well without query rewriting, the cases are not doing their job.

MULTI_TURN_SEEDS: list[tuple[str, str, str, str, list[SourceLocator], str]] = [
    ("Why are my webhooks failing?",
     "Webhook deliveries are retried with exponential backoff when your endpoint returns an error.",
     "what about the backoff schedule?",
     "The backoff schedule is described in the Webhooks Overview retry section.",
     [SourceLocator(source_type="docs", slug="webhooks-overview", heading="Backoff")],
     "pronoun-free follow-up, needs 'webhook' from turn 1"),
    ("What are the API rate limits?",
     "Limits are per plan; Growth allows 1,000 requests per minute.",
     "and what happens when I exceed them?",
     "Requests over the limit return HTTP 429 with a Retry-After header.",
     [SourceLocator(source_type="docs", slug="api-rate-limits", heading="429")],
     "'them' must resolve to rate limits"),
    ("How do I create an API key?",
     "API keys are created in the dashboard and can be scoped per resource.",
     "how do I rotate one?",
     "Create a new key, deploy it alongside the old one, then revoke the old key.",
     [SourceLocator(source_type="docs", slug="api-authentication", heading="Rotation")],
     "'one' must resolve to API key"),
    ("Tell me about data retention.",
     "Retention windows depend on your plan.",
     "can I export it before it expires?",
     "Export through the /v2/export endpoints; the /v1 endpoints were removed in v2.4.",
     # NOT the data-export doc. CL-2026-0610-03 SUPERSEDES it (ADR-009), so
     # ingestion set it is_current=false and retrieval will never return it.
     # The first version of this case expected the archived doc and the
     # resolver flagged it on the very first run — exactly the divergence the
     # unresolved-locator warning exists to catch. The changelog entry is now
     # the current source of truth, which makes this a better case anyway:
     # it verifies a superseded doc does NOT come back.
     [SourceLocator(source_type="changelog", entry_id="CL-2026-0610-03")],
     "'it' must resolve to retained data; ground truth is the changelog, "
     "because the data-export doc is deliberately superseded"),
]


def build_multi_turn() -> list[GoldenCase]:
    cases = []
    for index, (q1, a1, q2, reference, sources, note) in enumerate(MULTI_TURN_SEEDS, start=1):
        for tenant in TENANTS:
            cases.append(
                GoldenCase(
                    case_id=f"multi-{index:02d}-{tenant[:3]}",
                    case_type="multi_turn",
                    tenant_id=tenant,
                    query=q2,
                    history=[
                        {"role": "user", "content": q1},
                        {"role": "assistant", "content": a1},
                    ],
                    expected_sources=sources,
                    reference_answer=reference,
                    notes=note,
                )
            )
    return cases


# ---------------------------------------------------------------------------
# 5. OUT_OF_SCOPE — MUST abstain. The most important cases in the set.
# ---------------------------------------------------------------------------
# Three flavours, in rising order of difficulty:
#   (a) completely unrelated — the confidence gate should stop these cold
#   (b) plausible for a SaaS product but absent from this corpus — retrieval
#       returns topically-adjacent chunks, so the gate may pass and the MODEL
#       has to decline
#   (c) about a real Flowlytics feature but asking something the docs do not
#       say — the hardest, and where a helpful model invents an answer

OUT_OF_SCOPE_QUERIES = [
    ("What is the capital of France?", "a"),
    ("Write me a Python script to sort a list.", "a"),
    ("What is Flowlytics' stock price?", "b"),
    ("Who is the CEO of Flowlytics?", "b"),
    ("Does Flowlytics offer a mobile app for iOS?", "b"),
    ("What is the exact SLA uptime percentage for the Starter plan?", "c"),
    ("How many employees does Flowlytics have?", "b"),
    ("Can I run Flowlytics fully on-premise in my own datacenter?", "c"),
]


def build_out_of_scope() -> list[GoldenCase]:
    cases = []
    for index, (query, flavour) in enumerate(OUT_OF_SCOPE_QUERIES, start=1):
        for tenant in TENANTS:
            cases.append(
                GoldenCase(
                    case_id=f"oos-{index:02d}-{tenant[:3]}",
                    case_type="out_of_scope",
                    tenant_id=tenant,
                    query=query,
                    # Deliberately empty. There is nothing correct to retrieve,
                    # and that emptiness IS the assertion.
                    expected_sources=[],
                    reference_answer="I don't have enough information to answer this confidently.",
                    notes=f"must abstain (flavour {flavour})",
                )
            )
    return cases


# ---------------------------------------------------------------------------
# 6. CROSS_TENANT — MUST NOT leak (Design.md §8).
# ---------------------------------------------------------------------------
# Each tenant has private docs. Asking tenant A about tenant B's private
# content must return nothing of B's — and, because the content is genuinely
# absent for A, must also abstain.


def build_cross_tenant() -> list[GoldenCase]:
    cases = []
    private = {
        "acme": [d for d in ALL_DOCS if d.tenant == "acme"],
        "globex": [d for d in ALL_DOCS if d.tenant == "globex"],
    }
    for asking, other in (("acme", "globex"), ("globex", "acme")):
        for index, doc in enumerate(private[other], start=1):
            cases.append(
                GoldenCase(
                    case_id=f"xten-{asking[:3]}-{index:02d}",
                    case_type="cross_tenant",
                    tenant_id=asking,
                    # Names the other tenant's document explicitly. The whole
                    # point is that even an on-the-nose query cannot reach it.
                    query=f"What does the {doc.title} say?",
                    expected_sources=[],
                    reference_answer="I don't have enough information to answer this confidently.",
                    # A string that exists only in the other tenant's corpus.
                    forbidden_text=other,
                    notes=f"{asking} must not see {other}'s {doc.slug}",
                )
            )
    return cases


# ---------------------------------------------------------------------------


def build_all() -> list[GoldenCase]:
    cases = (
        build_normal()
        + build_exact_identifier()
        + build_stale_conflict()
        + build_multi_turn()
        + build_out_of_scope()
        + build_cross_tenant()
    )
    ids = [case.case_id for case in cases]
    duplicates = [case_id for case_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise SystemExit(f"duplicate case ids generated: {duplicates}")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--stats", action="store_true", help="print counts, write nothing")
    args = parser.parse_args()

    cases = build_all()
    counts = Counter(case.case_type for case in cases)

    print(f"{len(cases)} cases")
    for case_type, count in sorted(counts.items()):
        print(f"  {case_type:<18} {count:>3}")
    print(f"  {'tenants':<18} {sorted({c.tenant_id for c in cases})}")

    if args.stats:
        return 0

    if args.output.exists():
        print(
            f"\nWARNING: {args.output} exists and will be OVERWRITTEN. "
            "Hand edits will be lost — this file is meant to be edited after generation."
        )
        if input("overwrite? [y/N] ").strip().lower() != "y":
            print("aborted")
            return 1

    save_cases(args.output, cases)
    print(f"\nwrote {args.output}")
    print("Review and edit it — then commit. It is ground truth, so a diff is a decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
