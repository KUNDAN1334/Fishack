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
        cache=None,
    ):
        self.pool = pool
        self.embeddings = embeddings
        self.tokens = token_counter
        # Optional AnswerCache. When present, re-ingesting a document evicts
        # every cached answer built on its chunks (ADR-025). None means
        # ingestion runs without Redis — correct for tests and for a first
        # load, where there is nothing cached to invalidate.
        self.cache = cache

    def _get_chunker(self, source_type: str):
        """Which chunker handles this source type.

        A one-line extension point, added in Phase 4 so the chunking
        experiment can substitute `NaiveChunker` by SUBCLASSING rather than by
        adding a flag here. The production pipeline deliberately has no code
        path that produces naive chunks — an `if self.naive:` branch in the
        real ingester is a footgun that eventually fires in production.
        """
        return get_chunker(source_type, self.tokens)

    async def ingest_tenant(
        self,
        raw_dir: Path,
        tenant_id: str,
        tenant_name: str,
        force: bool = False,
        tenant_override: str | None = None,
    ) -> IngestionResult:
        """Ingest one tenant's whole corpus.

        `force=True` re-ingests even unchanged documents — used when the
        CHUNKING STRATEGY changed (the content hash is unchanged, but the
        chunks it produces are not). This is exactly the switch the Phase 4
        before/after chunking experiment needs.

        `tenant_override` reads the corpus from `tenant_id`'s directory but
        stores it under a different tenant. Phase 4 uses this to build the
        naive-chunking shadow tenants (`acme_naive`) from acme's source files:
        same input, different chunker, isolated by the same tenant mechanism
        that protects real customers.
        """
        result = IngestionResult()
        documents = load_tenant_corpus(raw_dir, tenant_id)
        logger.info("[%s] loaded %d source documents", tenant_id, len(documents))

        if tenant_override:
            # Rewrite ownership after loading. The loader derives tenant from
            # the directory tree, which is right for the real pipeline and
            # wrong for a shadow ingest.
            documents = [
                document.model_copy(update={"tenant_id": tenant_override})
                for document in documents
            ]
            tenant_id = tenant_override

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
        chunker = self._get_chunker(document.source_type)
        chunks = chunker.chunk(document)
        if not chunks:
            logger.warning("no chunks produced for %s", document.source_path)
            return result

        chunk_hashes = [content_hash(chunk.content) for chunk in chunks]
        embeddings = await self.embeddings.embed_passages([chunk.content for chunk in chunks])

        async with self.pool.acquire() as conn:
            # Chunk ids about to be REPLACED. Collected before the delete,
            # because after it they are gone and the answer cache would have
            # no way to know which cached answers are now stale (ADR-025).
            stale_chunk_ids = await self._chunk_ids_for_source(
                conn, document.tenant_id, document.source_path
            )

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

        # AFTER the transaction commits, never inside it. If invalidation ran
        # inside and the transaction then rolled back, we would have deleted
        # cache entries for content that still exists — harmless (a few extra
        # LLM calls) but confusing. The reverse is far worse: committing new
        # content while stale answers survive in the cache. Hence: commit
        # first, then invalidate.
        result.cache_entries_invalidated = await self._invalidate_cache(
            document.tenant_id, stale_chunk_ids
        )
        return result

    @staticmethod
    async def _chunk_ids_for_source(conn, tenant_id: str, source_path: str) -> list[str]:
        """Every chunk id currently serving this source path, current or not.

        Archived chunks are included on purpose: an answer cached before a
        supersession was built on chunks that are now `is_current=false`, and
        that answer is exactly the stale one we need to evict.
        """
        rows = await conn.fetch(
            """
            SELECT c.id FROM chunks c
              JOIN documents d ON d.id = c.document_id
             WHERE c.tenant_id = $1 AND d.source_path = $2
            """,
            tenant_id, source_path,
        )
        return [str(row["id"]) for row in rows]

    async def _invalidate_cache(self, tenant_id: str, chunk_ids: list[str]) -> int:
        """Evict cached answers built on chunks that just changed.

        Design.md §9: "active invalidation on ingestion of new/updated docs".
        Best-effort — a failed eviction costs staleness until TTL, and must
        never fail an ingest that already committed.
        """
        if self.cache is None or not chunk_ids:
            return 0
        try:
            return await self.cache.invalidate_chunks(tenant_id, chunk_ids)
        except Exception:  # noqa: BLE001
            logger.warning("cache invalidation failed after ingest", exc_info=True)
            return 0

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
