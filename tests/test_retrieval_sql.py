"""Retrieval SQL mechanics against a real Postgres.

Scope note, because it is easy to overreach here: these tests verify that the
SQL is CORRECT — it runs, it binds parameters the way we think, it uses the
operators we intend, it orders and limits properly, it round-trips vectors.

They do NOT verify retrieval QUALITY. The fixture uses FakeEncoder, whose
vectors are hashes, so nothing here can honestly claim "the vector leg finds
paraphrases the keyword leg misses". That is a quality claim, it needs real
embeddings and a labelled set, and it is exactly what the Phase 4 harness
measures. Asserting it with fake vectors would produce a green test that
means nothing — the same trap as a vacuous leakage test.

One test below is deliberately a PROBE rather than an assertion: how Postgres
tokenizes `ERR_TIMEOUT_502`. I did not want to guess the answer and write it
down as fact, so the test asserts the property we actually depend on (the
chunk is retrievable by that query) and prints the lexemes for the record.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.bm25 import search_bm25
from app.retrieval.tenant_scope import TenantScope
from app.retrieval.vector import format_vector, search_vector

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- BM25 leg --


async def test_bm25_leg_returns_scored_rows(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, chunks = await search_bm25(scope, "webhook retry backoff", limit=10)

    assert leg_result.ok
    assert leg_result.chunk_ids
    assert set(leg_result.scores) == set(leg_result.chunk_ids)
    assert all(score > 0 for score in leg_result.scores.values())
    # ts_rank_cd with normalization flag 32 squashes into (0, 1).
    assert all(0 < score < 1 for score in leg_result.scores.values())
    assert set(chunks) == set(leg_result.chunk_ids)


async def test_bm25_results_are_ordered_by_score_descending(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, _ = await search_bm25(scope, "webhook retry backoff signature", limit=10)

    scores = [leg_result.scores[chunk_id] for chunk_id in leg_result.chunk_ids]
    assert scores == sorted(scores, reverse=True)


async def test_bm25_survives_punctuation_that_would_break_to_tsquery(db_pool, seeded_corpus):
    """`to_tsvector` never raises on arbitrary text; `to_tsquery` does.

    A real support question is full of punctuation, and the keyword leg must
    not be able to 500 the endpoint. Using the same function that built the
    indexed `tsv` column also guarantees query and document are tokenized
    identically."""
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    for hostile in [
        "why does POST /v2/events return 502?",
        "webhook & retry | backoff",
        "what's the retry limit???",
        "'unbalanced quote",
        "",
    ]:
        leg_result, _ = await search_bm25(scope, hostile, limit=5)
        assert leg_result.ok, f"query {hostile!r} broke the BM25 leg: {leg_result.error}"


async def test_bm25_matches_documents_that_contain_only_SOME_query_terms(db_pool, seeded_corpus):
    """The regression test for the bug that shipped in my first version.

    Every convenient Postgres helper (`plainto_tsquery`, `websearch_to_tsquery`)
    ANDs its terms, which is boolean retrieval, not BM25. BM25 sums a per-term
    contribution over the terms a document DOES contain, so partial matches
    score — they just score lower.

    This query is built so that NO single chunk contains every lexeme: the
    docs chunk explains retries and names the error code but never says
    "limit", while the changelog entry says "limit" but names no error code.
    Under AND semantics this returned zero rows, the keyword leg contributed
    nothing, RRF quietly degenerated to vector-only, and "hybrid retrieval"
    became a claim in the README rather than a thing that happened.
    """
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, chunks = await search_bm25(scope, "webhook retry limit ERR_TIMEOUT_502", limit=10)

    assert leg_result.ok
    assert len(leg_result.chunk_ids) >= 2, (
        "the keyword leg must return partial matches; AND semantics would return 0 here"
    )

    # ...and cover density must rank the fuller match higher: the docs chunk
    # carries webhook + retry + err + timeout + 502, the changelog only
    # webhook + retry + limit.
    contents = [chunks[chunk_id].content for chunk_id in leg_result.chunk_ids]
    assert "ERR_TIMEOUT_502" in contents[0], (
        "ts_rank_cd should rank the chunk matching more query lexemes first"
    )


async def test_bm25_single_shared_term_is_enough_to_match(db_pool, seeded_corpus):
    """The other side of OR semantics: one shared stem is a (weak) match.

    This is correct for a leg feeding RRF, which only reads ranks — a weak
    match at rank 8 costs almost nothing, whereas a missing match costs
    everything.
    """
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, _ = await search_bm25(
        scope, "signature verification for inbound payloads", limit=10
    )
    assert leg_result.chunk_ids, "a query sharing only 'signature' must still match"


async def test_bm25_empty_query_matches_nothing_but_does_not_error(db_pool, seeded_corpus):
    """A stopword-only query produces an empty tsquery. Zero results is the
    correct answer, and must not look like a failure — Phase 3's gate reads
    'no candidates' as 'abstain', which is right; it must not read an error."""
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, chunks = await search_bm25(scope, "the and of", limit=5)

    assert leg_result.ok
    assert leg_result.chunk_ids == []
    assert chunks == {}


async def test_bm25_respects_the_limit(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, _ = await search_bm25(scope, "webhook", limit=1)
    assert len(leg_result.chunk_ids) <= 1


# ------------------------------------------- the identifier tokenization probe --


async def test_exact_identifier_is_retrievable(db_pool, seeded_corpus, capsys):
    """Design.md §5's headline claim for having a keyword leg at all.

    Postgres's default FTS parser treats `_` as a separator, so
    `ERR_TIMEOUT_502` is very likely indexed as three lexemes rather than one.
    That is fine for retrieval — a chunk containing all three in sequence is
    still a strong match — but it means we do NOT get true exact-identifier
    matching, and the difference matters if a corpus ever contains
    ERR_TIMEOUT_502 and ERR_TIMEOUT_504 side by side.

    So this test asserts the property we depend on (retrievable, top-ranked)
    and PRINTS the actual lexemes with `-s` so the behavior is recorded from
    evidence rather than from my assumption. See the ADR-001 footnote.
    """
    async with db_pool.acquire() as conn:
        lexemes = await conn.fetchval("SELECT to_tsvector('english', $1)::text", "ERR_TIMEOUT_502")
        ours = await conn.fetchval(
            """
            SELECT (
                SELECT string_agg(quote_literal(t.lexeme), ' | ')
                  FROM unnest(tsvector_to_array(to_tsvector('english', $1))) AS t(lexeme)
            )::tsquery::text
            """,
            "ERR_TIMEOUT_502",
        )
        anded = await conn.fetchval(
            "SELECT websearch_to_tsquery('english', $1)::text", "ERR_TIMEOUT_502"
        )
    print(f"\n  to_tsvector('ERR_TIMEOUT_502')          = {lexemes}")
    print(f"  our OR-ed tsquery                       = {ours}")
    print(f"  websearch_to_tsquery (AND, not used)    = {anded}")

    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, chunks = await search_bm25(scope, "ERR_TIMEOUT_502", limit=10)

    assert leg_result.chunk_ids, "the error code must be retrievable by the keyword leg"
    top_chunk = chunks[leg_result.chunk_ids[0]]
    assert "ERR_TIMEOUT_502" in top_chunk.content


# -------------------------------------------------------------- vector leg --


async def test_vector_leg_returns_cosine_similarities(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    query_vector = seeded_corpus["encoder"].encode_query("webhook retry")

    leg_result, chunks = await search_vector(scope, query_vector, limit=10, ef_search=100)

    assert leg_result.ok
    assert leg_result.chunk_ids
    # 1 - cosine_distance, and both sides are L2-normalized, so this is a
    # genuine cosine similarity in [-1, 1].
    assert all(-1.0001 <= score <= 1.0001 for score in leg_result.scores.values())


async def test_vector_leg_orders_by_similarity_descending(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    query_vector = seeded_corpus["encoder"].encode_query("anything")

    leg_result, _ = await search_vector(scope, query_vector, limit=10, ef_search=100)

    scores = [leg_result.scores[chunk_id] for chunk_id in leg_result.chunk_ids]
    assert scores == sorted(scores, reverse=True)


async def test_vector_leg_finds_a_chunk_by_its_own_stored_vector(db_pool, seeded_corpus):
    """The strongest thing fake embeddings CAN prove: a chunk's own vector
    retrieves that chunk at rank 1 with similarity ~1.0. This verifies the
    whole round trip — Python float list -> pgvector literal -> stored column
    -> `<=>` -> back — which is where dimension and formatting bugs live.
    """
    encoder = seeded_corpus["encoder"]
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])

    async with db_pool.acquire() as conn:
        content = await conn.fetchval(
            "SELECT content FROM chunks WHERE tenant_id = $1 ORDER BY id LIMIT 1",
            seeded_corpus["tenant_a"],
        )

    exact_vector = encoder.encode_passages([content])[0]
    leg_result, chunks = await search_vector(scope, exact_vector, limit=5, ef_search=100)

    assert chunks[leg_result.chunk_ids[0]].content == content
    assert leg_result.scores[leg_result.chunk_ids[0]] == pytest.approx(1.0, abs=1e-4)


async def test_empty_query_vector_degrades_rather_than_raising(db_pool, seeded_corpus):
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, chunks = await search_vector(scope, [], limit=5, ef_search=100)

    assert not leg_result.ok
    assert "empty query vector" in leg_result.error
    assert chunks == {}


async def test_wrong_dimension_vector_degrades_rather_than_raising(db_pool, seeded_corpus):
    """A model swap without a migration (ADR-005) shows up here. The leg must
    report the failure so hybrid retrieval degrades to BM25 — not take the
    whole request down."""
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    leg_result, _ = await search_vector(scope, [0.1] * 100, limit=5, ef_search=100)

    assert not leg_result.ok
    assert leg_result.error


async def test_ef_search_is_set_and_reverts_after_the_query(db_pool, seeded_corpus):
    """SET LOCAL must not leak onto the next user of a pooled connection.

    If it did, one retrieval could permanently change the search behavior of
    every later query on that connection — a performance bug that appears
    random because it depends on which pooled connection you got.
    """
    settings = get_settings()
    scope = TenantScope(db_pool, seeded_corpus["tenant_a"])
    query_vector = seeded_corpus["encoder"].encode_query("webhook")

    async with db_pool.acquire() as conn:
        before = await conn.fetchval("SHOW hnsw.ef_search")

    leg_result, _ = await search_vector(
        scope, query_vector, limit=5, ef_search=settings.hnsw_ef_search
    )
    assert leg_result.ok

    async with db_pool.acquire() as conn:
        after = await conn.fetchval("SHOW hnsw.ef_search")

    assert after == before, (
        f"hnsw.ef_search leaked out of the transaction ({before} -> {after}); "
        "SET LOCAL should have reverted it at commit"
    )


# --------------------------------------------------------------- plumbing --


def test_vector_formatting_matches_the_ingestion_side():
    """Query vectors and stored vectors must be formatted identically, or
    every distance carries a tiny invisible asymmetry."""
    from app.embeddings.service import _format_vector as ingestion_format

    vector = [0.123456789, -0.5, 1.0]
    assert format_vector(vector) == ingestion_format(vector)
