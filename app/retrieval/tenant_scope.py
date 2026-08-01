"""Tenant isolation, enforced structurally (Design.md §8).

Design.md §8 is explicit about what it wants: "enforced at the retrieval
SDK/query-builder level (not just application logic — bake it into a
middleware/wrapper so devs literally cannot query without it)."

This module is that wrapper. The rule it enforces:

    NOTHING in app/retrieval/ reads the chunks table except TenantScope.

A retrieval leg does not write a query. It writes a *fragment* — a projection,
a predicate, an ORDER BY — and hands it to `TenantScope.search()`, which
composes the real SQL with `WHERE c.tenant_id = $1 AND c.is_current` welded
on unconditionally. `$1` is reserved for the tenant id and bound here; leg
parameters start at `$2`. A leg has no syntactic way to reach the tenant
predicate, so "forgot the tenant filter" stops being a bug that can exist.

Four layers of defense, weakest to strongest:

  1. Composition       — the leg never writes FROM or WHERE tenant_id.
  2. Fragment guards   — a fragment mentioning tenant_id/is_current/$1 is
                         rejected at construction time (`LegQuery`).
  3. Runtime tripwire  — every returned row's tenant_id is re-checked against
                         the scope; a mismatch raises. This should be
                         unreachable, which is exactly why it is there:
                         Design.md §8's headline risk is *silent* leakage, and
                         this converts silent into loud.
  4. Source lint       — tests/test_tenant_scope.py asserts that `FROM chunks`
                         appears nowhere else in app/retrieval/.

PRODUCTION NOTE: a real team would add Postgres row-level security underneath
all of this — `ALTER TABLE chunks ENABLE ROW LEVEL SECURITY` with a policy on
`current_setting('app.tenant_id')`, set per request. Then even raw psql
sessions and future non-Python consumers are covered, and this module becomes
a convenience rather than the only thing standing between two customers. See
the closing note in 001_init.sql.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.retrieval.models import RetrievedChunk

logger = logging.getLogger(__name__)


class TenantIsolationError(RuntimeError):
    """A row for the wrong tenant came back from a scoped query.

    Unrecoverable by design: we do not filter it out and carry on, because a
    leak that gets quietly corrected in Python is a leak nobody investigates.
    """


class UnsafeLegQuery(ValueError):
    """A leg tried to write SQL that touches isolation concerns."""


# Columns every leg returns, so one row -> RetrievedChunk mapping works for
# all of them. Legs add their own scoring expression on top via `projection`.
_BASE_PROJECTION = """
    c.id            AS chunk_id,
    c.document_id   AS document_id,
    c.tenant_id     AS tenant_id,
    c.content       AS content,
    c.heading_path  AS heading_path,
    c.token_count   AS token_count,
    c.metadata      AS metadata,
    d.title         AS title,
    d.source_type   AS source_type,
    d.source_path   AS source_path,
    d.doc_version   AS doc_version,
    d.effective_date AS effective_date
"""

# Anything a leg is forbidden to mention. `tenant_id`/`is_current` because the
# scope owns them; `$1` because it is the tenant parameter; `;` because
# statement chaining would escape the composed query entirely.
_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\btenant_id\b", "tenant_id is owned by TenantScope, not by a leg"),
    (r"\bis_current\b", "is_current is owned by TenantScope (see include_archived)"),
    (r"\$1\b", "$1 is reserved for the tenant id; leg parameters start at $2"),
    (r";", "statement chaining is not allowed in a leg fragment"),
    (r"\bfrom\s+chunks\b", "legs do not write their own FROM clause"),
]

# SET LOCAL cannot take a bound parameter, so its value is interpolated. Only
# plain integers are ever allowed through — that keeps interpolation safe by
# construction rather than by careful review.
_SETTING_NAME = re.compile(r"^[a-z_]+\.[a-z_]+$")


@dataclass(frozen=True)
class LegQuery:
    """One retrieval leg's contribution to a query.

    Frozen so a validated fragment cannot be mutated after its guards ran.

    Attributes:
        leg:           name used in logs and as the RRF list key.
        projection:    the leg's own SELECT expressions, e.g.
                       "ts_rank_cd(c.tsv, q.tsq, 32) AS score".
        predicate:     the leg's own WHERE condition, ANDed after the tenant
                       predicate. Use "true" when the leg filters nothing.
        order_by:      ORDER BY body. Always end with a unique tiebreak
                       (c.id) or eval runs will not be reproducible.
        limit:         row cap.
        params:        values bound to $2, $3, ... in order.
        prelude:       optional SQL placed before the SELECT (a CTE, e.g.
                       "WITH q AS (SELECT websearch_to_tsquery(...) AS tsq)").
        joins:         optional extra FROM items, e.g. "CROSS JOIN q".
        local_settings: session settings applied with SET LOCAL inside the
                       query's transaction, e.g. {"hnsw.ef_search": 100}.
    """

    leg: str
    projection: str
    predicate: str
    order_by: str
    limit: int
    params: list[Any] = field(default_factory=list)
    prelude: str = ""
    joins: str = ""
    local_settings: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Guards run at construction, not at execution: an unsafe leg should
        # blow up the moment it is built, in the test that builds it.
        for fragment_name in ("projection", "predicate", "order_by", "prelude", "joins"):
            _assert_safe_fragment(fragment_name, getattr(self, fragment_name))
        if self.limit <= 0:
            raise UnsafeLegQuery(f"{self.leg}: limit must be positive, got {self.limit}")
        for name, value in self.local_settings.items():
            if not _SETTING_NAME.match(name):
                raise UnsafeLegQuery(f"{self.leg}: bad setting name {name!r}")
            if not isinstance(value, int) or isinstance(value, bool):
                raise UnsafeLegQuery(
                    f"{self.leg}: setting {name} must be a plain int "
                    f"(SET LOCAL cannot bind parameters), got {value!r}"
                )


def _assert_safe_fragment(name: str, sql: str) -> None:
    """Reject fragments that reach for isolation-critical SQL."""
    lowered = sql.lower()
    for pattern, why in _FORBIDDEN_PATTERNS:
        if re.search(pattern, lowered):
            raise UnsafeLegQuery(f"unsafe {name} fragment: {why}\n  fragment: {sql.strip()}")


class TenantScope:
    """A handle that can only ever read one tenant's chunks.

    Construct one per request from the authenticated tenant, then pass the
    SCOPE around — never the raw tenant id string. That way a function's
    signature shows whether it can reach the database at all, and there is no
    unbound `tenant_id: str` floating through the call graph waiting to be
    forgotten in a WHERE clause.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        *,
        include_archived: bool = False,
    ):
        # A falsy tenant id is the failure mode that matters: `""` or None
        # would otherwise compose into a query matching nothing (best case) or
        # everything (if a future refactor made the predicate conditional).
        # Refuse it at the door.
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError(
                f"TenantScope requires a non-empty tenant id, got {tenant_id!r}. "
                "There is deliberately no 'all tenants' mode."
            )
        self.pool = pool
        self.tenant_id = tenant_id
        # The ONE legitimate door to archived content: "what did the docs say
        # in v2.2?" (Design.md §3 allows it when the user asks explicitly).
        # It is a property of the scope, not something a leg can toggle.
        self.include_archived = include_archived

    def __repr__(self) -> str:  # keeps tenant visible in tracebacks
        return f"TenantScope(tenant_id={self.tenant_id!r}, include_archived={self.include_archived})"

    # ------------------------------------------------------------- search --

    async def search(self, leg: LegQuery) -> list[asyncpg.Record]:
        """Run a leg query, tenant-scoped. The only read path to `chunks`."""
        sql = self._compose(leg)
        params = [self.tenant_id, *leg.params]

        async with self.pool.acquire() as conn:
            # A transaction is required for SET LOCAL to mean anything — it
            # reverts at commit, so we cannot leak a raised ef_search onto the
            # next user of this pooled connection.
            async with conn.transaction():
                for name, value in leg.local_settings.items():
                    await conn.execute(f"SET LOCAL {name} = {int(value)}")
                rows = await conn.fetch(sql, *params)

        self._assert_no_foreign_rows(leg, rows)
        return rows

    def _compose(self, leg: LegQuery) -> str:
        """Weld the tenant predicate onto the leg's fragments.

        Written as one readable f-string rather than a builder object: you
        should be able to see the entire executed query, tenant filter
        included, without following any indirection. That readability IS the
        security property here.
        """
        archived_predicate = "" if self.include_archived else "\n           AND c.is_current = true"
        return f"""
        {leg.prelude}
        SELECT {_BASE_PROJECTION.strip()},
               {leg.projection.strip()}
          FROM chunks c
          JOIN documents d ON d.id = c.document_id
          {leg.joins}
         WHERE c.tenant_id = $1{archived_predicate}
           AND ({leg.predicate.strip()})
         ORDER BY {leg.order_by.strip()}
         LIMIT {int(leg.limit)}
        """

    def _assert_no_foreign_rows(self, leg: LegQuery, rows: list[asyncpg.Record]) -> None:
        """Tripwire. Should never fire; must be deafening if it does.

        We deliberately do NOT filter the offending rows out and continue.
        Serving a slightly-wrong result set that nobody notices is the exact
        failure Design.md §8 calls out; crashing produces an incident.
        """
        foreign = {row["tenant_id"] for row in rows if row["tenant_id"] != self.tenant_id}
        if foreign:
            logger.critical(
                "TENANT LEAK: leg=%s scope=%s returned rows for %s",
                leg.leg, self.tenant_id, sorted(foreign),
            )
            raise TenantIsolationError(
                f"leg {leg.leg!r} scoped to {self.tenant_id!r} returned rows for "
                f"{sorted(foreign)} — isolation is broken, refusing to serve"
            )


def row_to_chunk(row: asyncpg.Record) -> RetrievedChunk:
    """Map a scoped row onto the shared retrieval type.

    Lives here because this module owns the row shape (`_BASE_PROJECTION`);
    putting it anywhere else would let the two drift apart.
    """
    return RetrievedChunk(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        tenant_id=row["tenant_id"],
        content=row["content"],
        heading_path=row["heading_path"],
        token_count=row["token_count"] or 0,
        metadata=_parse_jsonb(row["metadata"]),
        title=row["title"] or "",
        source_type=row["source_type"] or "",
        source_path=row["source_path"] or "",
        doc_version=row["doc_version"],
        effective_date=row["effective_date"],
    )


def _parse_jsonb(value: Any) -> dict:
    """asyncpg hands back JSONB as a str unless a codec is registered.

    Parse defensively so this works either way — the same defensive read the
    embedding cache does for vectors. A malformed value degrades to {} with a
    warning rather than killing a whole retrieval.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        logger.warning("could not parse chunk metadata as JSON: %r", value)
        return {}
    return parsed if isinstance(parsed, dict) else {}
