"""Generate the synthetic Flowlytics corpus into data/raw/.

Layout produced (one tree per tenant — tenancy is visible in the filesystem,
which makes the isolation story concrete before any code enforces it):

    data/raw/acme/docs/webhooks-overview.md      (markdown + YAML frontmatter)
    data/raw/acme/changelog.jsonl                (one JSON object per entry)
    data/raw/acme/tickets.jsonl                  (one JSON object per ticket)
    data/raw/globex/...

Three formats on purpose: the ingestion pipeline then has three genuinely
different parsing paths, matching Design.md §3's three source systems.

Usage:
    python scripts/generate_corpus.py                # LLM prose (cached)
    python scripts/generate_corpus.py --offline      # no LLM, template prose
    python scripts/generate_corpus.py --only acme    # one tenant
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm.client import build_llm_client  # noqa: E402
from data.generation import spec  # noqa: E402
from data.generation.prose import ProseGenerator  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("generate_corpus")


def _frontmatter(doc: spec.DocSpec, tenant: str) -> str:
    """YAML frontmatter carrying the versioning metadata Design.md §3 demands.

    The loader reads these into the `documents` row — the metadata is part of
    the source of truth, not something ingestion invents.
    """
    return (
        "---\n"
        f"slug: {doc.slug}\n"
        f"title: {doc.title}\n"
        f"tenant: {tenant}\n"
        f"product_area: {doc.product_area}\n"
        f"doc_version: {doc.version}\n"
        f"effective_date: {doc.effective_date.isoformat()}\n"
        f"source_type: docs\n"
        "---\n\n"
    )


def _render_table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    """Markdown table. Tables are a deliberate chunker edge case: they must
    never be split mid-table (tested in tests/test_chunker_docs.py)."""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def _table_rows(headers: tuple[str, ...], doc: spec.DocSpec) -> list[list[str]]:
    """Deterministic placeholder rows derived from the headers.

    Tables are STRUCTURE, not prose — we generate them in code so the shape
    is guaranteed valid markdown (LLMs are unreliable at table syntax, and a
    malformed table would corrupt the chunker's table detection).
    """
    seeds = {
        "Plan": ["Starter", "Growth", "Enterprise"],
        "Role": ["Owner", "Admin", "Analyst", "Viewer"],
        "Code": ["ERR_TIMEOUT_502", "ERR_RATE_LIMITED", "ERR_INVALID_KEY", "ERR_SCHEMA_MISMATCH"],
        "Severity": ["P1", "P2", "P3"],
        "Format": ["CSV", "JSON", "Parquet"],
        "Event": ["event.created", "event.updated", "invoice.paid"],
        "Region": ["us-east", "eu-central", "eu-west"],
        "Widget": ["Line chart", "Funnel", "Retention grid"],
        "Integration": ["Slack", "Salesforce", "Snowflake", "Segment"],
        "Scope": ["events:read", "events:write", "billing:read"],
    }
    first = headers[0]
    labels = seeds.get(first, [f"{first} {i}" for i in range(1, 4)])
    rows = []
    for i, label in enumerate(labels):
        row = [label]
        for header in headers[1:]:
            row.append(_cell_value(header, i, doc))
        rows.append(row)
    return rows


def _cell_value(header: str, index: int, doc: spec.DocSpec) -> str:
    h = header.lower()
    if "price" in h or "per" in h or "$" in h:
        return ["$0", "$499", "Custom"][index % 3]
    if "requests" in h or "rows" in h or "events" in h:
        return ["100", "1,000", "Unlimited"][index % 3]
    if "status" in h:
        return ["400", "429", "502"][index % 3]
    if "since" in h or "version" in h:
        return doc.version
    if h.startswith("can ") or "required" in h:
        return ["Yes", "No"][index % 2]
    return ["Standard", "Extended", "Custom"][index % 3]


async def build_doc_markdown(gen: ProseGenerator, doc: spec.DocSpec, tenant: str) -> str:
    """Assemble one doc page: frontmatter + H1 + H2/H3 sections with prose."""
    parts = [_frontmatter(doc, tenant), f"# {doc.title}\n"]
    context = f"the '{doc.title}' page ({doc.product_area}, {doc.version})"

    for section in doc.sections:
        parts.append(f"\n## {section.heading}\n")
        words = "260-340 words" if section.long else "90-150 words"
        parts.append(await gen.generate(context, section.hint, words) + "\n")

        if section.table:
            parts.append("\n" + _render_table(section.table, _table_rows(section.table, doc)) + "\n")

        for sub_heading, sub_hint in section.subsections:
            parts.append(f"\n### {sub_heading}\n")
            parts.append(await gen.generate(f"{context}, section '{section.heading}'",
                                            sub_hint, "70-110 words") + "\n")
    return "\n".join(parts)


async def build_changelog_entry(gen: ProseGenerator, entry: spec.ChangelogSpec) -> dict:
    body = await gen.generate(
        f"the Flowlytics {entry.version} changelog entry '{entry.title}'",
        entry.hint,
        "45-80 words",  # changelog entries are atomic and SHORT (Design.md §4)
    )
    return {
        "entry_id": entry.entry_id,
        "version": entry.version,
        "date": entry.date.isoformat(),
        "title": entry.title,
        "kind": entry.kind,
        "product_area": entry.product_area,
        "body": body,
        # These drive the versioning logic at ingestion time
        "supersedes": entry.supersedes,
        "conflicts_with": entry.conflicts_with,
    }


async def build_ticket(gen: ProseGenerator, ticket: spec.TicketSpec) -> dict:
    context = f"a resolved Flowlytics support ticket titled '{ticket.subject}'"
    question = await gen.generate(
        context + " — write the CUSTOMER's message",
        ticket.question_hint + ". Write in first person as the customer, including the error "
        "code verbatim if one is mentioned",
        "50-90 words",
    )
    answer = await gen.generate(
        context + " — write the SUPPORT AGENT's resolving reply",
        ticket.answer_hint + ". Write as a support engineer explaining cause and fix",
        "70-120 words",
    )
    return {
        "ticket_id": ticket.ticket_id,
        "subject": ticket.subject,
        "question": question,
        "answer": answer,
        "product_area": ticket.product_area,
        "resolution_tag": ticket.resolution_tag,
        "error_code": ticket.error_code,
        "resolved_date": ticket.resolved_date.isoformat(),
        "status": "resolved",
    }


async def generate_tenant(gen: ProseGenerator, tenant: str) -> dict[str, int]:
    tenant_dir = RAW_DIR / tenant
    (tenant_dir / "docs").mkdir(parents=True, exist_ok=True)

    docs = spec.docs_for_tenant(tenant)
    for i, doc in enumerate(docs, 1):
        markdown = await build_doc_markdown(gen, doc, tenant)
        (tenant_dir / "docs" / f"{doc.slug}.md").write_text(markdown, encoding="utf-8")
        logger.info("[%s] doc %d/%d %s", tenant, i, len(docs), doc.slug)

    entries = spec.changelog_for_tenant(tenant)
    with (tenant_dir / "changelog.jsonl").open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(await build_changelog_entry(gen, entry)) + "\n")
    logger.info("[%s] %d changelog entries", tenant, len(entries))

    tickets = spec.tickets_for_tenant(tenant)
    with (tenant_dir / "tickets.jsonl").open("w", encoding="utf-8") as fh:
        for ticket in tickets:
            fh.write(json.dumps(await build_ticket(gen, ticket)) + "\n")
    logger.info("[%s] %d tickets", tenant, len(tickets))

    return {"docs": len(docs), "changelog": len(entries), "tickets": len(tickets)}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="skip the LLM entirely (cache + template prose only)")
    parser.add_argument("--only", help="generate a single tenant (acme|globex)")
    args = parser.parse_args()

    settings = get_settings()
    client = None
    if not args.offline:
        try:
            client = build_llm_client(settings)
        except ValueError as exc:
            logger.warning("no LLM configured (%s) — running offline", exc)

    gen = ProseGenerator(client)
    tenants = [args.only] if args.only else list(spec.TENANTS)

    print("Corpus plan:", json.dumps(spec.corpus_summary(), indent=2))
    totals: dict[str, int] = {}
    for tenant in tenants:
        if tenant not in spec.TENANTS:
            logger.error("unknown tenant %r", tenant)
            return 1
        counts = await generate_tenant(gen, tenant)
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value

    print(f"\nWrote to {RAW_DIR}: {totals}")
    print(f"Prose: {gen.stats}")
    if gen.stats["fact_warnings"]:
        print("WARNING: some generated prose dropped required literals — "
              "check the log; re-running will regenerate only those sections.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
