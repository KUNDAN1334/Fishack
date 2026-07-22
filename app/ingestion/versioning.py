"""Versioning and supersession (Design.md §3 and §11a).

"Stale data hallucination ka root cause almost hamesha missing/wrong metadata
hota hai — isliye main ingestion time hi pe strong versioning discipline
enforce karta hoon, generation time pe patch nahi karta."

Three mechanisms, in increasing subtlety:

1. REPLACEMENT. Re-ingesting the same source_path with different content
   archives the old document (is_current=false) and inserts a new one. Soft,
   never a DELETE — Design.md §3 wants the old version kept for audit, and
   a trace from last week must still be able to show what was cited then.

2. EXPLICIT SUPERSESSION. A changelog entry declaring `supersedes: <slug>`
   archives that doc. This is the clean case where someone remembered to
   record the relationship.

3. UNMARKED CONFLICT. A changelog entry declaring `conflicts_with: <slug>`
   leaves BOTH live and records the relationship in metadata. This is the
   realistic case, and it is deliberately NOT auto-archived: the newer
   changelog contradicts one FACT in the doc, not the whole page. Archiving
   the page would destroy correct information; so the conflict is pushed to
   generation time, where Design.md §7 rule 4 applies — prefer the newest
   source and flag the discrepancy.

That third case is the whole reason the corpus plants both kinds.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


async def archive_document(conn: asyncpg.Connection, document_id, reason: str) -> int:
    """Mark a document and all its chunks is_current=false.

    Chunks carry their own is_current (denormalized, like tenant_id) so the
    retrieval filter never needs a join. Both must be flipped together —
    inside one transaction at the call site.
    """
    await conn.execute("UPDATE documents SET is_current = false WHERE id = $1", document_id)
    updated = await conn.execute(
        "UPDATE chunks SET is_current = false WHERE document_id = $1", document_id
    )
    logger.info("archived document %s (%s), chunks: %s", document_id, reason, updated)
    return int(updated.split()[-1]) if updated else 0


async def archive_previous_versions(
    conn: asyncpg.Connection, tenant_id: str, source_path: str, keep_document_id
) -> int:
    """Archive earlier documents at the same source_path for this tenant.

    Scoped by (tenant_id, source_path) — the identity of "the same document
    over time". Note it is NOT scoped by content_hash: the whole point is
    that the content changed.
    """
    rows = await conn.fetch(
        """
        SELECT id FROM documents
        WHERE tenant_id = $1 AND source_path = $2 AND id <> $3 AND is_current = true
        """,
        tenant_id, source_path, keep_document_id,
    )
    for row in rows:
        await archive_document(conn, row["id"], f"superseded by newer version of {source_path}")
    return len(rows)


async def apply_supersessions(
    conn: asyncpg.Connection, tenant_id: str, supersede_slugs: list[str]
) -> int:
    """Archive docs named by changelog `supersedes` declarations.

    Matches on the source_path containing the slug (docs live at
    .../docs/<slug>.md). Only touches source_type='docs' — a changelog entry
    can retire a doc page, never another changelog entry, which is immutable
    history.
    """
    archived = 0
    for slug in supersede_slugs:
        rows = await conn.fetch(
            """
            SELECT id FROM documents
            WHERE tenant_id = $1
              AND source_type = 'docs'
              AND source_path LIKE $2
              AND is_current = true
            """,
            tenant_id, f"%{slug}.md",
        )
        for row in rows:
            await archive_document(conn, row["id"], f"superseded by changelog ({slug})")
            archived += 1
        if not rows:
            # Loud, because a typo'd slug means a stale doc silently stays live
            logger.warning("supersedes target %r matched no live doc for tenant %s",
                           slug, tenant_id)
    return archived


async def record_conflicts(
    conn: asyncpg.Connection, tenant_id: str, conflicts: list[tuple[str, str]]
) -> int:
    """Tag chunks of a doc that a newer changelog entry contradicts.

    Writes `conflicts_with_entry` into the doc chunk's metadata. Retrieval
    (Phase 2) and generation (Phase 3) can then detect "this chunk is known
    to be contested" without re-deriving the relationship, and the eval
    harness can select these chunks as the stale-data conflict cases.

    `conflicts` is [(doc_slug, changelog_entry_id), ...].
    """
    tagged = 0
    for slug, entry_id in conflicts:
        result = await conn.execute(
            """
            UPDATE chunks
               SET metadata = metadata || jsonb_build_object('conflicts_with_entry', $3::text)
             WHERE tenant_id = $1
               AND is_current = true
               AND document_id IN (
                   SELECT id FROM documents
                    WHERE tenant_id = $1 AND source_type = 'docs' AND source_path LIKE $2
               )
            """,
            tenant_id, f"%{slug}.md", entry_id,
        )
        count = int(result.split()[-1]) if result else 0
        tagged += count
        if count == 0:
            logger.warning("conflicts_with target %r matched no live chunks for tenant %s",
                           slug, tenant_id)
    return tagged
