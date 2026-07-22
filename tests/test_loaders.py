"""Loaders: three source formats -> ParsedDocument.

Also pins the "only resolved tickets" rule from Design.md §3 — indexing an
unresolved thread means retrieving an unverified answer with full confidence.
"""

import datetime as dt
import json

from app.ingestion.loaders import (
    load_changelog,
    load_doc,
    load_tenant_corpus,
    load_tickets,
    parse_frontmatter,
)

DOC_MD = """---
slug: webhooks-overview
title: Webhooks Overview
tenant: acme
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---

# Webhooks Overview

## Retry Logic

Retries use exponential backoff with a maximum of 3 attempts.
"""


def test_parse_frontmatter_extracts_keys_and_body():
    meta, body = parse_frontmatter(DOC_MD)
    assert meta["doc_version"] == "v2.2"
    assert meta["slug"] == "webhooks-overview"
    assert body.lstrip().startswith("# Webhooks Overview")


def test_parse_frontmatter_tolerates_missing_block():
    meta, body = parse_frontmatter("# No frontmatter\n\ntext")
    assert meta == {}
    assert body.startswith("# No frontmatter")


def test_load_doc_maps_metadata(tmp_path):
    path = tmp_path / "webhooks-overview.md"
    path.write_text(DOC_MD, encoding="utf-8")
    doc = load_doc(path, "acme")
    assert doc.tenant_id == "acme"
    assert doc.source_type == "docs"
    assert doc.title == "Webhooks Overview"
    assert doc.doc_version == "v2.2"
    assert doc.effective_date == dt.date(2026, 3, 12)
    # The chunker needs the heading structure, so content keeps the markdown
    assert "## Retry Logic" in doc.content


def test_load_changelog_yields_one_document_per_entry(tmp_path):
    path = tmp_path / "changelog.jsonl"
    entries = [
        {"entry_id": "CL-1", "version": "v2.4", "date": "2026-06-10", "title": "A",
         "kind": "changed", "product_area": "platform", "body": "body a",
         "supersedes": "data-export", "conflicts_with": None},
        {"entry_id": "CL-2", "version": "v2.3", "date": "2026-04-02", "title": "B",
         "kind": "added", "product_area": "billing", "body": "body b",
         "supersedes": None, "conflicts_with": "billing-invoices"},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    docs = load_changelog(path, "acme")
    assert len(docs) == 2
    assert docs[0].extra["supersedes"] == "data-export"
    assert docs[1].extra["conflicts_with"] == "billing-invoices"
    # Per-entry source_path so each entry is independently citable
    assert docs[0].source_path.endswith("#CL-1")
    assert docs[0].effective_date == dt.date(2026, 6, 10)


def test_load_changelog_skips_malformed_lines(tmp_path):
    """One bad line must not lose the rest of the file."""
    path = tmp_path / "changelog.jsonl"
    good = {"entry_id": "CL-1", "version": "v2.4", "date": "2026-06-10", "title": "A",
            "kind": "changed", "product_area": "platform", "body": "b"}
    path.write_text(json.dumps(good) + "\n{ not json }\n", encoding="utf-8")
    assert len(load_changelog(path, "acme")) == 1


def test_load_tickets_skips_unresolved(tmp_path):
    path = tmp_path / "tickets.jsonl"
    rows = [
        {"ticket_id": "ACM-1", "subject": "S1", "question": "q", "answer": "a",
         "product_area": "platform", "resolution_tag": "config",
         "error_code": "ERR_TIMEOUT_502", "resolved_date": "2026-05-03", "status": "resolved"},
        {"ticket_id": "ACM-2", "subject": "S2", "question": "q", "answer": "",
         "product_area": "billing", "resolution_tag": None, "error_code": None,
         "resolved_date": "2026-05-04", "status": "open"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    docs = load_tickets(path, "acme")
    assert len(docs) == 1
    assert docs[0].extra["ticket_id"] == "ACM-1"
    assert docs[0].extra["error_code"] == "ERR_TIMEOUT_502"


def test_load_tenant_corpus_reads_all_three_sources(tmp_path):
    tenant_dir = tmp_path / "acme"
    (tenant_dir / "docs").mkdir(parents=True)
    (tenant_dir / "docs" / "a.md").write_text(DOC_MD, encoding="utf-8")
    (tenant_dir / "changelog.jsonl").write_text(json.dumps(
        {"entry_id": "CL-1", "version": "v2.4", "date": "2026-06-10", "title": "A",
         "kind": "changed", "product_area": "platform", "body": "b"}) + "\n", encoding="utf-8")
    (tenant_dir / "tickets.jsonl").write_text(json.dumps(
        {"ticket_id": "T-1", "subject": "S", "question": "q", "answer": "a",
         "product_area": "platform", "resolution_tag": "bug", "error_code": None,
         "resolved_date": "2026-05-01", "status": "resolved"}) + "\n", encoding="utf-8")

    docs = load_tenant_corpus(tmp_path, "acme")
    assert {d.source_type for d in docs} == {"docs", "changelog", "ticket"}
    assert all(d.tenant_id == "acme" for d in docs)
