"""Tenant isolation enforcement — the guards, without a database.

Design.md §8's requirement is that a developer "literally cannot query
without" the tenant filter. That is a claim about the SHAPE of the code, so
most of it is testable without Postgres: the composed SQL, the fragment
guards, the tripwire, and a source lint over the whole package.

The end-to-end proof (query tenant A, get zero tenant B rows) lives in
tests/test_tenant_isolation.py, which needs a real database.
"""

from pathlib import Path

import pytest

from app.retrieval.bm25 import build_bm25_leg
from app.retrieval.tenant_scope import (
    LegQuery,
    TenantIsolationError,
    TenantScope,
    UnsafeLegQuery,
    row_to_chunk,
)
from app.retrieval.vector import build_vector_leg

RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "app" / "retrieval"


def safe_leg(**overrides) -> LegQuery:
    kwargs = dict(
        leg="test", projection="1.0 AS score", predicate="true",
        order_by="score DESC, c.id", limit=10,
    )
    kwargs.update(overrides)
    return LegQuery(**kwargs)


class FakeRow(dict):
    """asyncpg.Record is dict-like for our purposes."""


# --------------------------------------------------------- scope creation --


@pytest.mark.parametrize("bad", ["", "   ", None, 123, [], {}])
def test_scope_refuses_a_missing_tenant(bad):
    """The dangerous input is a falsy tenant id: it composes into a query
    matching nothing today, and — one conditional-predicate refactor later —
    everything. Refuse at the door; there is deliberately no 'all tenants'
    mode."""
    with pytest.raises(ValueError, match="non-empty tenant id"):
        TenantScope(pool=None, tenant_id=bad)


def test_scope_repr_shows_the_tenant():
    """Tracebacks and logs should say which tenant a failing query belonged
    to without anyone having to add a log line."""
    assert "acme" in repr(TenantScope(pool=None, tenant_id="acme"))


# ------------------------------------------------------- fragment guards --


@pytest.mark.parametrize(
    "field,fragment,expected",
    [
        ("predicate", "c.tenant_id = 'globex'", "tenant_id"),
        ("projection", "c.tenant_id AS leak", "tenant_id"),
        ("predicate", "c.is_current = false", "is_current"),
        ("predicate", "c.content LIKE $1", r"\$1"),
        ("predicate", "true; DROP TABLE chunks", "chaining"),
        ("prelude", "WITH x AS (SELECT id FROM chunks)", "FROM clause"),
        ("order_by", "score DESC; --", "chaining"),
    ],
)
def test_unsafe_fragments_are_rejected_at_construction(field, fragment, expected):
    """Guards fire when the leg is BUILT, so an unsafe leg fails in the test
    that builds it rather than in production at 3am."""
    with pytest.raises(UnsafeLegQuery, match=expected):
        safe_leg(**{field: fragment})


def test_limit_must_be_positive():
    with pytest.raises(UnsafeLegQuery, match="limit must be positive"):
        safe_leg(limit=0)


@pytest.mark.parametrize("bad_value", ["100; DROP TABLE chunks", 1.5, True, None])
def test_local_settings_accept_only_plain_ints(bad_value):
    """SET LOCAL cannot bind a parameter, so its value is interpolated into
    SQL. Restricting it to plain ints makes that interpolation safe by
    construction rather than by careful review. `True` is excluded explicitly
    because bool is a subclass of int in Python."""
    with pytest.raises(UnsafeLegQuery):
        safe_leg(local_settings={"hnsw.ef_search": bad_value})


def test_local_setting_names_are_validated():
    with pytest.raises(UnsafeLegQuery, match="bad setting name"):
        safe_leg(local_settings={"hnsw.ef_search = 1; SELECT": 100})


def test_legs_are_frozen_after_validation():
    """A validated fragment must not be mutable afterwards, or the guards
    would be a formality."""
    leg = safe_leg()
    with pytest.raises(Exception):
        leg.predicate = "c.tenant_id = 'globex'"


# ------------------------------------------------------------ composition --


def test_composed_sql_always_carries_the_tenant_predicate():
    scope = TenantScope(pool=None, tenant_id="acme")
    sql = scope._compose(safe_leg())
    assert "WHERE c.tenant_id = $1" in sql
    assert "AND c.is_current = true" in sql
    assert "FROM chunks c" in sql


def test_include_archived_is_the_only_way_past_is_current():
    """Design.md §3 allows explicitly asking for an old version. That door
    belongs to the SCOPE, not to a leg fragment."""
    default = TenantScope(pool=None, tenant_id="acme")._compose(safe_leg())
    archived = TenantScope(pool=None, tenant_id="acme", include_archived=True)._compose(safe_leg())

    assert "is_current" in default
    assert "is_current" not in archived
    assert "WHERE c.tenant_id = $1" in archived  # tenant filter never optional


def test_real_legs_compose_cleanly():
    """The two production legs must survive their own guards."""
    scope = TenantScope(pool=None, tenant_id="acme")

    bm25_sql = scope._compose(build_bm25_leg("ERR_TIMEOUT_502", 20))
    assert "to_tsvector" in bm25_sql
    assert "ts_rank_cd" in bm25_sql
    assert "WHERE c.tenant_id = $1" in bm25_sql

    vector_sql = scope._compose(build_vector_leg([0.1] * 384, 20, ef_search=100))
    assert "<=>" in vector_sql
    assert "WHERE c.tenant_id = $1" in vector_sql


def test_bm25_leg_uses_or_semantics_not_and():
    """Pinned in a pure test so the regression is caught without a database.

    `plainto_tsquery`/`websearch_to_tsquery` AND their terms, which turns the
    keyword leg into a boolean filter returning nothing for most realistic
    multi-concept queries. BM25 is an OR-ed, summed-score retriever: a
    document matching 4 of 6 terms still scores, it just scores lower.
    """
    leg = build_bm25_leg("webhook retry limit", 20)
    assert "' | '" in leg.prelude, "lexemes must be OR-ed"
    assert "websearch_to_tsquery" not in leg.prelude
    assert "plainto_tsquery" not in leg.prelude


def test_vector_leg_orders_by_distance_not_similarity():
    """Ordering by `1 - distance DESC` is the same ranking but Postgres would
    not recognize it as index-servable and would sequential-scan every chunk.
    This assertion is the only thing standing between us and a silent 100x
    slowdown that still returns correct results."""
    leg = build_vector_leg([0.1] * 384, 20, ef_search=100)
    assert leg.order_by.startswith("c.embedding <=> $2::vector")


def test_leg_params_start_at_dollar_two():
    """$1 belongs to the tenant. A leg that assumed $1 was its own would
    silently search for the tenant id as a keyword."""
    leg = build_bm25_leg("webhook retry", 20)
    assert leg.params == ["webhook retry"]
    assert "$2" in leg.prelude


# -------------------------------------------------------------- tripwire --


def test_foreign_rows_raise_instead_of_being_filtered_out():
    """We do not quietly drop the offending rows and carry on. Design.md §8's
    headline risk is SILENT leakage; a leak that Python corrects invisibly is
    a leak nobody ever investigates."""
    scope = TenantScope(pool=None, tenant_id="acme")
    rows = [FakeRow(tenant_id="acme"), FakeRow(tenant_id="globex")]

    with pytest.raises(TenantIsolationError, match="globex"):
        scope._assert_no_foreign_rows(safe_leg(), rows)


def test_clean_rows_pass_the_tripwire():
    scope = TenantScope(pool=None, tenant_id="acme")
    scope._assert_no_foreign_rows(safe_leg(), [FakeRow(tenant_id="acme")] * 3)
    scope._assert_no_foreign_rows(safe_leg(), [])


# ------------------------------------------------------------ source lint --


def test_only_tenant_scope_reads_the_chunks_table():
    """The structural claim, enforced mechanically.

    If someone adds a "quick debug query" to service.py six months from now,
    this fails. It is 10 lines and it is the difference between a convention
    and a rule.
    """
    offenders = []
    for path in sorted(RETRIEVAL_DIR.glob("*.py")):
        if path.name == "tenant_scope.py":
            continue
        text = path.read_text(encoding="utf-8").lower()
        # Strip docstrings/comments crudely: we care about executable SQL, and
        # several modules legitimately DISCUSS the chunks table in prose.
        code = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith("#")
        )
        if "from chunks" in code:
            offenders.append(path.name)

    assert offenders == [], (
        f"{offenders} query the chunks table directly. All reads must go "
        "through TenantScope so the tenant predicate cannot be omitted."
    )


def test_no_module_builds_its_own_tenant_predicate():
    """Belt and braces: nobody should be writing `tenant_id =` in SQL outside
    the scope, even in a query that does not touch `chunks`."""
    offenders = []
    for path in sorted(RETRIEVAL_DIR.glob("*.py")):
        if path.name == "tenant_scope.py":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "tenant_id =" in line and "$" in line:
                offenders.append(f"{path.name}: {stripped}")

    assert offenders == [], f"hand-written tenant predicates found: {offenders}"


# ----------------------------------------------------------- row mapping --


def test_row_to_chunk_parses_jsonb_metadata_from_a_string():
    """asyncpg returns JSONB as a str unless a codec is registered. Parsing
    defensively means this works either way."""
    row = FakeRow(
        chunk_id="c1", document_id="d1", tenant_id="acme", content="body",
        heading_path="Webhooks > Retry", token_count=120,
        metadata='{"conflicts_with_entry": "CL-2026-0610-01"}',
        title="Webhooks", source_type="docs", source_path="p.md",
        doc_version="v2.2", effective_date=None,
    )
    chunk = row_to_chunk(row)
    assert chunk.metadata["conflicts_with_entry"] == "CL-2026-0610-01"
    assert chunk.is_contested is True


def test_row_to_chunk_survives_unparseable_metadata():
    """Bad metadata degrades one chunk's extras; it must not kill a whole
    retrieval."""
    row = FakeRow(
        chunk_id="c1", document_id="d1", tenant_id="acme", content="body",
        heading_path=None, token_count=None, metadata="not json",
        title=None, source_type=None, source_path=None,
        doc_version=None, effective_date=None,
    )
    chunk = row_to_chunk(row)
    assert chunk.metadata == {}
    assert chunk.is_contested is False
    assert chunk.token_count == 0
