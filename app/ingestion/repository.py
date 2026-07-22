"""All SQL writes for ingestion.

Kept in one file so the transaction boundaries are visible in one place: a
document and its chunks must land atomically, or retrieval could see a
document with half its chunks — which looks like a retrieval bug and is
miserable to diagnose.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from app.ingestion.models import ParsedDocument, ProtoChunk

logger = logging.getLogger(__name__)


async def ensure_tenant(conn: asyncpg.Connection, tenant_id: str, name: str) -> None:
    await conn.execute(
        """
        INSERT INTO tenants (id, name) VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
        """,
        tenant_id, name,
    )


async def find_document_by_hash(
    conn: asyncpg.Connection, tenant_id: str, content_hash: str
):
    """Dedup probe: has this exact content already been ingested for this
    tenant? Uses the UNIQUE(tenant_id, content_hash) index."""
    return await conn.fetchrow(
        "SELECT id, is_current FROM documents WHERE tenant_id = $1 AND content_hash = $2",
        tenant_id, content_hash,
    )


async def insert_document(
    conn: asyncpg.Connection, document: ParsedDocument, content_hash: str
):
    """Insert the documents row and return its id."""
    return await conn.fetchval(
        """
        INSERT INTO documents (
            tenant_id, source_type, title, source_path, doc_version,
            effective_date, product_area, content_hash, is_current
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true)
        RETURNING id
        """,
        document.tenant_id, document.source_type, document.title, document.source_path,
        document.doc_version, document.effective_date, document.product_area, content_hash,
    )


async def delete_chunks(conn: asyncpg.Connection, document_id) -> None:
    """Remove a document's chunks before re-inserting.

    Needed because UNIQUE(document_id, chunk_index) means a re-chunk that
    produces FEWER chunks would otherwise leave orphaned high-index rows
    behind — stale content that still matches queries. Delete-then-insert
    inside one transaction is simpler and safer than a diffing upsert.
    """
    await conn.execute("DELETE FROM chunks WHERE document_id = $1", document_id)


async def insert_chunks(
    conn: asyncpg.Connection,
    document_id,
    tenant_id: str,
    chunks: list[ProtoChunk],
    chunk_hashes: list[str],
    embeddings: list[list[float]],
) -> int:
    """Bulk-insert chunks with their vectors.

    executemany over a list of tuples: one round trip's worth of protocol
    overhead instead of one per chunk. tenant_id is passed EXPLICITLY on
    every row rather than derived by the DB — the isolation-critical column
    should be impossible to forget, and a missing value fails loudly here.
    """
    if not chunks:
        return 0
    records = [
        (
            document_id,
            tenant_id,
            chunk.chunk_index,
            chunk.content,
            chunk_hash,
            chunk.heading_path,
            chunk.token_count,
            json.dumps(chunk.metadata),
            _format_vector(embedding),
        )
        for chunk, chunk_hash, embedding in zip(chunks, chunk_hashes, embeddings)
    ]
    await conn.executemany(
        """
        INSERT INTO chunks (
            document_id, tenant_id, chunk_index, content, content_hash,
            heading_path, token_count, metadata, embedding, is_current
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::vector, true)
        """,
        records,
    )
    return len(records)


async def corpus_stats(conn: asyncpg.Connection) -> list[dict]:
    """Per-tenant, per-source counts for the CLI `stats` command."""
    rows = await conn.fetch(
        """
        SELECT d.tenant_id,
               d.source_type,
               count(DISTINCT d.id)                          AS documents,
               count(c.id)                                   AS chunks,
               count(c.id) FILTER (WHERE c.is_current)       AS current_chunks,
               round(avg(c.token_count))                     AS avg_tokens,
               max(c.token_count)                            AS max_tokens,
               min(c.token_count)                            AS min_tokens
          FROM documents d
          LEFT JOIN chunks c ON c.document_id = d.id
         GROUP BY d.tenant_id, d.source_type
         ORDER BY d.tenant_id, d.source_type
        """
    )
    return [dict(row) for row in rows]


def _format_vector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"
