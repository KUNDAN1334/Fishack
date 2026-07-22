"""Read the three raw source formats into ParsedDocument.

Deliberately three separate functions with three separate parsers, because
that's what real ingestion looks like (Design.md §3: a docs CMS, a CI/CD
changelog hook, and a helpdesk API — three systems, three shapes). A single
"universal loader" would only work because we generated all three ourselves.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

from app.ingestion.models import ParsedDocument

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract the simple `key: value` frontmatter block.

    A real pipeline would use PyYAML; our frontmatter is flat key-value by
    construction, so a 6-line parser avoids the dependency and stays
    inspectable. PRODUCTION NOTE: use a real YAML parser the moment
    frontmatter gains nested structures or lists.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def _relative(path: Path) -> str:
    """Repo-relative path for the `source_path` provenance column."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def load_doc(path: Path, tenant_id: str) -> ParsedDocument:
    """One markdown docs page."""
    raw = path.read_text(encoding="utf-8")
    meta, _body = parse_frontmatter(raw)
    return ParsedDocument(
        tenant_id=tenant_id,
        source_type="docs",
        title=meta.get("title", path.stem),
        source_path=_relative(path),
        # NOTE: we hash and chunk the FULL text including frontmatter-stripped
        # headings — the chunker needs the heading structure, so it gets `raw`
        # and strips frontmatter itself.
        content=raw,
        effective_date=dt.date.fromisoformat(
            meta.get("effective_date", dt.date.today().isoformat())
        ),
        doc_version=meta.get("doc_version"),
        product_area=meta.get("product_area"),
        extra={"slug": meta.get("slug", path.stem)},
    )


def load_changelog(path: Path, tenant_id: str) -> list[ParsedDocument]:
    """changelog.jsonl -> one ParsedDocument PER ENTRY.

    Each entry becomes its own `documents` row, not one row for the whole
    file. That's what makes per-entry versioning (`effective_date`,
    `is_current`) and per-entry citation possible — a changelog file has no
    single meaningful date.
    """
    documents = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.error("%s:%d malformed JSON, skipping: %s", path, line_number, exc)
            continue
        documents.append(
            ParsedDocument(
                tenant_id=tenant_id,
                source_type="changelog",
                title=entry["title"],
                source_path=f"{_relative(path)}#{entry['entry_id']}",
                content=entry["body"],
                effective_date=dt.date.fromisoformat(entry["date"]),
                doc_version=entry["version"],
                product_area=entry.get("product_area"),
                extra={
                    "entry_id": entry["entry_id"],
                    "kind": entry.get("kind"),
                    "version": entry["version"],
                    "supersedes": entry.get("supersedes"),
                    "conflicts_with": entry.get("conflicts_with"),
                },
            )
        )
    return documents


def load_tickets(path: Path, tenant_id: str) -> list[ParsedDocument]:
    """tickets.jsonl -> one ParsedDocument per resolved ticket.

    Only resolved tickets are ingested (Design.md §3: "Only resolved +
    verified tickets") — an unresolved thread has no verified answer, so
    indexing it would mean retrieving a wrong answer with full confidence.
    """
    documents = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ticket = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.error("%s:%d malformed JSON, skipping: %s", path, line_number, exc)
            continue
        if ticket.get("status") != "resolved":
            logger.info("skipping unresolved ticket %s", ticket.get("ticket_id"))
            continue
        documents.append(
            ParsedDocument(
                tenant_id=tenant_id,
                source_type="ticket",
                title=ticket["subject"],
                source_path=f"{_relative(path)}#{ticket['ticket_id']}",
                # Hash over the Q&A pair: an edited answer must produce a new
                # hash so re-ingestion notices the change.
                content=f"{ticket['question']}\n\n{ticket['answer']}",
                effective_date=dt.date.fromisoformat(ticket["resolved_date"]),
                product_area=ticket.get("product_area"),
                extra={
                    "ticket_id": ticket["ticket_id"],
                    "question": ticket["question"],
                    "answer": ticket["answer"],
                    "resolution_tag": ticket.get("resolution_tag"),
                    "error_code": ticket.get("error_code"),
                },
            )
        )
    return documents


def load_tenant_corpus(raw_dir: Path, tenant_id: str) -> list[ParsedDocument]:
    """Everything for one tenant, in a stable order.

    Sorted so ingestion is deterministic run-to-run — which matters because
    chunk_index and therefore chunk identity depend on ordering.
    """
    tenant_dir = raw_dir / tenant_id
    if not tenant_dir.exists():
        raise FileNotFoundError(
            f"No corpus for tenant {tenant_id!r} at {tenant_dir}. "
            f"Run: python scripts/generate_corpus.py"
        )

    documents: list[ParsedDocument] = []
    docs_dir = tenant_dir / "docs"
    if docs_dir.exists():
        for path in sorted(docs_dir.glob("*.md")):
            documents.append(load_doc(path, tenant_id))

    changelog_path = tenant_dir / "changelog.jsonl"
    if changelog_path.exists():
        documents.extend(load_changelog(changelog_path, tenant_id))

    tickets_path = tenant_dir / "tickets.jsonl"
    if tickets_path.exists():
        documents.extend(load_tickets(tickets_path, tenant_id))

    return documents
