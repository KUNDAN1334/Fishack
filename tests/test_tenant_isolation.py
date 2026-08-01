"""THE leakage test (Design.md §8, point 4).

    "Automated leakage testing — CI pipeline test: query tenant A, assert
     zero results from tenant B's namespace."

The important part of this file is not the assertion that A's results contain
no B rows. That assertion is easy to write and easy to write WRONG: it passes
when the index is empty, when the sentinel is misspelled, when the fixture
silently failed to insert tenant B at all, or when the query matches nothing
for either tenant. A leakage test that passes for the wrong reason is worse
than no leakage test, because it retires the question.

So every test below is paired with a CONTROL that proves the thing it is
asserting the absence of was actually present and findable. If the control
fails, the test errors out loudly instead of quietly passing.

The fixture (conftest.py) gives both tenants near-identical webhook docs, so
the ONLY thing keeping tenant B's chunk out of tenant A's results is the
tenant predicate. Remove `WHERE c.tenant_id = $1` from tenant_scope.py and
every test here fails — which is the property we actually want to guarantee.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.embeddings.service import EmbeddingService
from app.retrieval.service import RetrievalService
from app.retrieval.tenant_scope import TenantIsolationError, TenantScope
from tests.fakes import FakeReranker

pytestmark = pytest.mark.integration

QUERY = "webhook retry limit ERR_TIMEOUT_502"


def build_service(db_pool, seeded_corpus) -> RetrievalService:
    settings = get_settings()
    embeddings = EmbeddingService(db_pool, seeded_corpus["encoder"])
    # A fake reranker keeps torch out of CI. Isolation is enforced before the
    # reranker ever sees a candidate, so a real cross-encoder would add
    # minutes of runtime and prove nothing extra.
    return RetrievalService(embeddings, settings, reranker=FakeReranker({"webhook": 3.0}))


# ----------------------------------------------------- the control first --


async def test_control_the_sentinel_is_findable_without_a_tenant_filter(db_pool, seeded_corpus):
    """Guard against a vacuous suite.

    Before asserting "tenant A never sees the sentinel", prove the sentinel
    exists, is indexed, and is retrievable by this query — using raw SQL that
    deliberately bypasses TenantScope. If this test ever fails, every other
    test in this file is meaningless and you must fix the fixture before
    trusting them.
    """
    tenants = [seeded_corpus["tenant_a"], seeded_corpus["tenant_b"]]

    async with db_pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM chunks WHERE tenant_id = $1", seeded_corpus["tenant_b"]
        )
        by_content = await conn.fetchval(
            "SELECT count(*) FROM chunks WHERE content LIKE $1",
            f"%{seeded_corpus['sentinel']}%",
        )
        # ...and that the FTS index (not just the column) can reach it, using
        # the SAME tsquery construction the BM25 leg uses.
        #
        # SCOPED TO THE TEST TENANTS ON PURPOSE. The first version of this
        # control counted matches across the whole `chunks` table, so the real
        # acme/globex corpus satisfied it while the test tenants matched
        # nothing at all — the control passed vacuously while guarding against
        # vacuousness. That is not a hypothetical: it is exactly how it failed
        # the first time it was run against a populated database, and it is
        # why anti-vacuity controls must be scoped as tightly as the thing
        # they are vouching for.
        by_fts = await conn.fetchval(
            """
            SELECT count(*) FROM chunks
             WHERE tenant_id = ANY($1::text[])
               AND tsv @@ (
                   SELECT string_agg(quote_literal(t.lexeme), ' | ')
                     FROM unnest(tsvector_to_array(to_tsvector('english', $2))) AS t(lexeme)
               )::tsquery
            """,
            tenants, QUERY,
        )
        per_tenant = await conn.fetch(
            """
            SELECT tenant_id, count(*) AS n FROM chunks
             WHERE tenant_id = ANY($1::text[])
               AND tsv @@ (
                   SELECT string_agg(quote_literal(t.lexeme), ' | ')
                     FROM unnest(tsvector_to_array(to_tsvector('english', $2))) AS t(lexeme)
               )::tsquery
             GROUP BY tenant_id
            """,
            tenants, QUERY,
        )

    assert total > 0, "fixture failed: tenant B has no chunks"
    assert by_content == 1, "fixture failed: the sentinel is not in the corpus"
    assert by_fts >= 2, (
        f"fixture failed: the test query matches only {by_fts} chunk(s) across the two "
        "TEST tenants, so an isolation test using it would pass vacuously"
    )
    # Both tenants must be reachable by this query, or "tenant A never sees
    # tenant B's rows" is trivially true for the wrong reason.
    matched = {row["tenant_id"] for row in per_tenant}
    assert matched == set(tenants), (
        f"fixture failed: only {matched} match the test query; both tenants must, "
        "or the isolation assertions prove nothing"
    )


# ------------------------------------------------------------- the tests --


@pytest.mark.parametrize("mode", ["bm25", "vector", "hybrid"])
async def test_no_cross_tenant_chunks_in_any_retrieval_mode(db_pool, seeded_corpus, mode):
    """Every retrieval path is isolated, not just the default one.

    Parametrized deliberately: a leak introduced in the vector leg alone
    would be invisible to a test that only exercises hybrid, because BM25
    could be supplying all the top results.
    """
    service = build_service(db_pool, seeded_corpus)
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])

    result = await service.retrieve(scope, QUERY, mode=mode, top_k=20)

    assert result.results, f"mode={mode} returned nothing; the test would be vacuous"
    for scored in result.candidates:
        assert scored.chunk.tenant_id == seeded_corpus["tenant_a"]
        assert seeded_corpus["sentinel"] not in scored.chunk.content


async def test_reranked_results_are_isolated_too(db_pool, seeded_corpus):
    """The reranker reorders candidates; it must never be able to introduce
    one. Asserted separately because reranking is where a future 'fetch a bit
    more context' optimization would most plausibly reach back into the DB."""
    service = build_service(db_pool, seeded_corpus)
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])

    result = await service.retrieve(scope, QUERY, mode="hybrid", top_k=5)

    assert result.rerank is not None and result.rerank.reranked is True
    assert result.results
    assert all(s.chunk.tenant_id == seeded_corpus["tenant_a"] for s in result.results)


async def test_the_other_tenant_sees_its_own_sentinel(db_pool, seeded_corpus):
    """The mirror image, and the second half of the non-vacuousness proof:
    isolation must not be 'tenant A gets nothing'. Tenant B queries the same
    text and DOES get the sentinel chunk. Only then does tenant A's absence
    of it mean something."""
    service = build_service(db_pool, seeded_corpus)
    scope = TenantScope(db_pool, seeded_corpus["tenant_b"])

    result = await service.retrieve(scope, QUERY, mode="hybrid", top_k=20)

    contents = " ".join(s.chunk.content for s in result.candidates)
    assert seeded_corpus["sentinel"] in contents
    assert all(s.chunk.tenant_id == seeded_corpus["tenant_b"] for s in result.candidates)


async def test_archived_chunks_stay_out_by_default(db_pool, seeded_corpus):
    """`is_current` is enforced in the same place as `tenant_id`, so stale
    content cannot leak into an answer either (Design.md §3). Archive tenant
    A's doc and confirm it disappears — then confirm the explicit door works.
    """
    service = build_service(db_pool, seeded_corpus)
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])

    before = await service.retrieve(scope, QUERY, mode="bm25", top_k=20)
    assert before.candidates, "test would be vacuous"

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE chunks SET is_current = false WHERE tenant_id = $1",
            seeded_corpus["tenant_a"],
        )

    after = await service.retrieve(scope, QUERY, mode="bm25", top_k=20)
    assert after.candidates == []

    # The one legitimate way past the filter — a property of the SCOPE, never
    # of a leg fragment.
    archived_scope = TenantScope(db_pool, seeded_corpus["tenant_a"], include_archived=True)
    archived = await service.retrieve(archived_scope, QUERY, mode="bm25", top_k=20)
    assert archived.candidates
    assert all(s.chunk.tenant_id == seeded_corpus["tenant_a"] for s in archived.candidates)


async def test_tripwire_fires_when_isolation_is_broken(db_pool, seeded_corpus):
    """Prove the last line of defense actually works.

    We cannot easily make the composed SQL leak — that is the point of the
    design — so we verify the tripwire directly against rows it should
    reject. Without this, layer 3 of tenant_scope.py is untested code that
    everyone assumes works.
    """
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])

    async with db_pool.acquire() as conn:
        foreign_rows = await conn.fetch(
            "SELECT tenant_id FROM chunks WHERE tenant_id = $1", seeded_corpus["tenant_b"]
        )
    assert foreign_rows, "fixture failed: no tenant B rows to test the tripwire with"

    from app.retrieval.tenant_scope import LegQuery

    leg = LegQuery(leg="probe", projection="1.0 AS score", predicate="true",
                   order_by="c.id", limit=1)
    with pytest.raises(TenantIsolationError, match=seeded_corpus["tenant_b"]):
        scope._assert_no_foreign_rows(leg, foreign_rows)
