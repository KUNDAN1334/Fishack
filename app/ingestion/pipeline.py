"""The ingestion orchestrator (Design.md §3).

    Source files
        -> load        (loaders.py:  three formats -> ParsedDocument)
        -> dedup       (dedup.py:    content hash; unchanged => skip)
        -> chunk       (chunkers/:   strategy per source_type)
        -> embed       (embeddings/: cache-first, batch the misses)
        -> upsert      (repository:  document + chunks, one transaction)
        -> version     (versioning:  archive old, apply supersessions,
                                     tag unmarked conflicts)

Ordering note: supersessions run AFTER all documents are ingested, because a
changelog entry may supersede a doc that appears later in the same run.
Doing it inline would make the outcome depend on file ordering — a bug that
would only show up as "sometimes the stale doc is still live".
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from app.embeddings.service import EmbeddingService
from app.ingestion import repository, versioning
from app.ingestion.chunkers import get_chunker
from app.ingestion.dedup import content_hash
from app.ingestion.loaders import load_tenant_corpus
from app.ingestion.models import IngestionResult, ParsedDocument
from app.ingestion.tokenizer import TokenCounter

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embeddings: EmbeddingService,
        token_counter: TokenCounter,
    ):
        self.pool = pool
        self.embeddings = embeddings
        self.tokens = token_counter

    async def ingest_tenant(
        self, raw_dir: Path, tenant_id: str, tenant_name: str, force: bool = False
    ) -> IngestionResult:
        """Ingest one tenant's whole corpus.

        `force=True` re-ingests even unchanged documents — used when the
        CHUNKING STRATEGY changed (the content hash is unchanged, but the
        chunks it produces are not). This is exactly the switch the Phase 4
        before/after chunking experiment needs.
        """
        result = IngestionResult()
        documents = load_tenant_corpus(raw_dir, tenant_id)
        logger.info("[%s] loaded %d source documents", tenant_id, len(documents))

        async with self.pool.acquire() as conn:
            await repository.ensure_tenant(conn, tenant_id, tenant_name)

        for document in documents:
            try:
                result.merge(await self._ingest_one(document, force=force))
            except Exception as exc:  # noqa: BLE001
                # One bad document must not abort a 150-document run.
                logger.exception("failed to ingest %s", document.source_path)
                result.errors.append(f"{document.source_path}: {exc}")

        result.merge(await self._apply_versioning(tenant_id, documents))

        result.embeddings_from_cache = self.embeddings.stats["hits"]
        result.embeddings_computed = self.embeddings.stats["misses"]
        return result

    # ------------------------------------------------------------ internals --

    async def _ingest_one(self, document: ParsedDocument, force: bool) -> IngestionResult:
        result = IngestionResult()
        doc_hash = content_hash(document.content)

        async with self.pool.acquire() as conn:
            existing = await repository.find_document_by_hash(conn, document.tenant_id, doc_hash)

        if existing and not force:
            # Identical content already ingested for this tenant: no-op.
            # This is what makes re-running ingestion cheap and safe.
            result.documents_skipped_duplicate = 1
            return result

        # Chunk BEFORE opening the transaction: chunking is pure CPU and
        # embedding hits the network/model — holding a DB transaction open
        # across either would pin a connection for no reason.
        chunker = get_chunker(document.source_type, self.tokens)
        chunks = chunker.chunk(document)
        if not chunks:
            logger.warning("no chunks produced for %s", document.source_path)
            return result

        chunk_hashes = [content_hash(chunk.content) for chunk in chunks]
        embeddings = await self.embeddings.embed_passages([chunk.content for chunk in chunks])

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if existing:
                    # force=True path: same content, re-chunking. Replace in
                    # place rather than creating a second identical document
                    # (which UNIQUE(tenant_id, content_hash) would reject).
                    document_id = existing["id"]
                    await repository.delete_chunks(conn, document_id)
                else:
                    document_id = await repository.insert_document(conn, document, doc_hash)
                    result.documents_ingested = 1
                    result.documents_superseded += await versioning.archive_previous_versions(
                        conn, document.tenant_id, document.source_path, document_id
                    )

                result.chunks_written = await repository.insert_chunks(
                    conn, document_id, document.tenant_id, chunks, chunk_hashes, embeddings
                )
        return result

    async def _apply_versioning(
        self, tenant_id: str, documents: list[ParsedDocument]
    ) -> IngestionResult:
        """Second pass: changelog-driven supersession and conflict tagging."""
        result = IngestionResult()

        supersedes = [
            d.extra["supersedes"] for d in documents
            if d.source_type == "changelog" and d.extra.get("supersedes")
        ]
        conflicts = [
            (d.extra["conflicts_with"], d.extra.get("entry_id", ""))
            for d in documents
            if d.source_type == "changelog" and d.extra.get("conflicts_with")
        ]

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if supersedes:
                    result.documents_superseded += await versioning.apply_supersessions(
                        conn, tenant_id, supersedes
                    )
                if conflicts:
                    tagged = await versioning.record_conflicts(conn, tenant_id, conflicts)
                    logger.info("[%s] tagged %d chunks with unmarked conflicts", tenant_id, tagged)
        return result
