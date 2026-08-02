"""Resolving stable locators to chunk ids (ADR-019).

Runs once at the start of an eval, against whatever corpus is currently
loaded. The golden set says "the Retry Logic section of webhooks-overview";
this turns that into the chunk ids that section currently occupies.

Why a section can resolve to SEVERAL chunks: the docs chunker splits long
sections and carries ~15% overlap, so "Webhooks > Retry Logic" may be two or
three chunks. All of them count as correct retrievals — the case is asking
"did we find the right passage", and any chunk of that section is the right
passage. Requiring one specific chunk would make recall depend on chunk
boundaries, which is exactly the variable the chunking experiment changes.

Unresolved locators are reported, never silently dropped. A locator matching
nothing means the golden set and the corpus have diverged — someone renamed a
heading, or the ingest did not run — and without a loud signal it presents as
a catastrophic recall regression with no cause.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import asyncpg

from fishnet.models import GoldenCase, SourceLocator

logger = logging.getLogger(__name__)


@dataclass
class ResolvedCase:
    """A case with its ground truth turned into concrete chunk ids."""

    case: GoldenCase
    expected_chunk_ids: set[str] = field(default_factory=set)
    unresolved: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """Out-of-scope cases legitimately expect nothing. Everything else
        needs at least one resolved chunk, or it can only ever score zero."""
        if self.case.must_abstain:
            return True
        return bool(self.expected_chunk_ids)


class LocatorResolver:
    """Resolves locators against a live corpus, with a per-run cache.

    The cache matters: a 60-case golden set contains many repeated locators
    (several questions about the same webhooks page), and each resolution is a
    query. Caching turns ~150 queries into ~40.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._cache: dict[tuple, set[str]] = {}

    async def resolve_case(self, case: GoldenCase) -> ResolvedCase:
        resolved = ResolvedCase(case=case)
        for locator in case.expected_sources:
            chunk_ids = await self.resolve(case.tenant_id, locator)
            if not chunk_ids:
                resolved.unresolved.append(locator.describe())
                logger.warning(
                    "case %s: locator %s resolved to nothing for tenant %s",
                    case.case_id, locator.describe(), case.tenant_id,
                )
            resolved.expected_chunk_ids |= chunk_ids
        return resolved

    async def resolve(self, tenant_id: str, locator: SourceLocator) -> set[str]:
        key = (
            tenant_id, locator.source_type, locator.slug,
            locator.heading, locator.entry_id, locator.ticket_id,
        )
        if key in self._cache:
            return self._cache[key]

        chunk_ids = await self._query(tenant_id, locator)
        self._cache[key] = chunk_ids
        return chunk_ids

    async def _query(self, tenant_id: str, locator: SourceLocator) -> set[str]:
        """One query per locator shape.

        Note `is_current = true` throughout: ground truth refers to what a
        query SHOULD retrieve, and retrieval only ever returns current chunks.
        A superseded doc must resolve to nothing — that is the point of the
        stale-data cases, and expecting archived chunks would make them pass
        for the wrong reason.
        """
        async with self.pool.acquire() as conn:
            if locator.source_type == "docs":
                # `slug` matches the filename stem in source_path. Heading is a
                # substring match on heading_path, so "Retry Logic" also picks
                # up its subsections ("... > Retry Logic > Backoff Schedule"),
                # which is what a reader would consider the same passage.
                rows = await conn.fetch(
                    """
                    SELECT c.id
                      FROM chunks c
                      JOIN documents d ON d.id = c.document_id
                     WHERE c.tenant_id = $1
                       AND c.is_current = true
                       AND d.source_type = 'docs'
                       AND d.source_path LIKE '%' || $2 || '.md'
                       AND ($3::text IS NULL OR c.heading_path ILIKE '%' || $3 || '%')
                    """,
                    tenant_id, locator.slug, locator.heading,
                )
            elif locator.source_type == "changelog":
                rows = await conn.fetch(
                    """
                    SELECT c.id FROM chunks c
                     WHERE c.tenant_id = $1 AND c.is_current = true
                       AND c.metadata->>'entry_id' = $2
                    """,
                    tenant_id, locator.entry_id,
                )
            else:  # ticket
                rows = await conn.fetch(
                    """
                    SELECT c.id FROM chunks c
                     WHERE c.tenant_id = $1 AND c.is_current = true
                       AND c.metadata->>'ticket_id' = $2
                    """,
                    tenant_id, locator.ticket_id,
                )
        return {str(row["id"]) for row in rows}


async def resolve_all(
    pool: asyncpg.Pool, cases: list[GoldenCase]
) -> tuple[list[ResolvedCase], list[str]]:
    """Resolve a whole golden set. Returns (resolved, warnings).

    Resolution happens up front, before any retrieval or generation, so a
    stale golden set fails in seconds rather than after twenty minutes of
    LLM calls.
    """
    resolver = LocatorResolver(pool)
    resolved: list[ResolvedCase] = []
    warnings: list[str] = []

    for case in cases:
        item = await resolver.resolve_case(case)
        resolved.append(item)
        if item.unresolved:
            warnings.append(
                f"{case.case_id}: {len(item.unresolved)} locator(s) unresolved "
                f"({', '.join(item.unresolved)})"
            )
        elif not item.is_usable:
            warnings.append(f"{case.case_id}: no expected chunks — case cannot score above 0")

    return resolved, warnings
