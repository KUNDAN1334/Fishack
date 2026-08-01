"""The keyword leg: BM25-style ranking via Postgres full-text search.

Design.md §5 wants a lexical matcher beside the vector one, because embedding
similarity is bad at exactly the things B2B support queries are full of:
error codes, API endpoint names, version numbers. "ERR_TIMEOUT_502" has no
useful semantic neighborhood — you want the chunk that literally contains it.

ADR-001 chose Postgres FTS over `rank_bm25` and over Elasticsearch: one
datastore means one tenant predicate enforced in SQL for both legs, one
backup story, and a `tsv` generated column that cannot drift from `content`.
The honest caveat, also in ADR-001: `ts_rank_cd` is not BM25 — no document
length normalization, no IDF saturation. It matters less than it sounds like
it should, because RRF (fusion.py) consumes ranks and throws the scores away.

PRODUCTION NOTE: with heterogeneous document lengths or a much larger corpus,
swap this leg for OpenSearch/Vespa (true BM25) or ParadeDB's pg_search
(BM25 inside Postgres). The leg interface below would not change — which is
the point of keeping each leg behind one function.
"""

from __future__ import annotations

import logging
import time

from app.retrieval.models import LEG_BM25, LegResult, RetrievedChunk
from app.retrieval.tenant_scope import LegQuery, TenantScope, row_to_chunk

logger = logging.getLogger(__name__)

# ts_rank_cd normalization flag 32 = "divide the rank by itself + 1", which
# squashes an otherwise unbounded score into (0, 1). RRF does not care (it
# uses ranks), but the playground display and Phase 3's confidence gate need
# a number that does not depend on how long the document happened to be.
_RANK_NORMALIZATION = 32


# Build the tsquery by OR-ing the query's own lexemes.
#
# THIS IS THE MOST IMPORTANT FOUR LINES IN THE FILE, and the first version got
# it wrong, so the reasoning is worth spelling out.
#
# Every convenient Postgres helper ANDs its terms:
#   plainto_tsquery('webhook retry limit')      -> 'webhook' & 'retri' & 'limit'
#   websearch_to_tsquery('webhook retry limit') -> 'webhook' & 'retri' & 'limit'
#
# AND is *boolean retrieval*: a document must contain EVERY query term or it
# does not match at all. That is not what BM25 does. BM25 scores a document by
# SUMMING a per-term contribution over the terms it does contain — a document
# matching 4 of 6 query terms still scores, just lower than one matching 6.
# Ranked retrieval is inherently OR-ed; the ranking function, not the matcher,
# decides what wins.
#
# The practical consequence of getting this wrong is severe and quiet. With
# AND semantics, the realistic support query
#     "webhook retry limit ERR_TIMEOUT_502"
# returns ZERO rows against our corpus, because the docs page explains the
# retry behavior and names the error code while the changelog entry is the one
# that says "limit" — no single chunk holds all six lexemes. The keyword leg
# then contributes nothing, RRF degenerates to vector-only, and "hybrid
# retrieval" is a claim in the README rather than a thing that happens. No
# error, no log line, and the arm you would blame is the one still working.
#
# So we lex the query with to_tsvector (which normalizes, stems, and drops
# stopwords exactly as the indexed `tsv` column was built) and join the
# resulting lexemes with `|`. `quote_literal` wraps each lexeme so a lexeme
# containing a quote cannot break the cast. Zero lexemes (an all-stopword
# query) yields NULL, and `tsv @@ NULL` matches nothing — the correct answer,
# reached without an error.
#
# PRODUCTION NOTE: OR semantics matches far more rows, so Postgres scores more
# candidates per query. At our scale (~2k chunks) that is microseconds. On a
# large corpus you would want the ranking pushed into the index — a real BM25
# engine (OpenSearch/Vespa) or ParadeDB's pg_search — rather than a GIN scan
# feeding ts_rank_cd.
_LEXEME_OR_TSQUERY = """
WITH q AS (
    SELECT (
        SELECT string_agg(quote_literal(t.lexeme), ' | ')
          FROM unnest(tsvector_to_array(to_tsvector('english', $2))) AS t(lexeme)
    )::tsquery AS tsq
)
"""


def build_bm25_leg(query: str, limit: int) -> LegQuery:
    """Build the FTS leg fragment. Pure — no I/O, so it is directly testable.

    Two independent choices are baked in here:

    1. OR semantics over the query's lexemes — see `_LEXEME_OR_TSQUERY` above.
       This is what makes the leg a *ranked* retriever rather than a boolean
       filter, and it is the difference between hybrid retrieval working and
       silently not working.

    2. `to_tsvector` as the parser. Like `websearch_to_tsquery` and unlike
       `to_tsquery`, it never raises on ordinary punctuation — a real support
       question ("why does POST /v2/events return 502?") must not 500 the
       endpoint. Using the same function that built the indexed `tsv` column
       also guarantees query and document are tokenized identically, which is
       one fewer place for a stemming mismatch to hide.

    What we give up by not using `websearch_to_tsquery`: quoted phrases and
    `-exclusion`. Both are nice, neither is worth AND semantics. If Phase 4
    shows identifier queries need true phrase matching, the fix is to add a
    phrase-detecting branch here — not to change fusion.
    """
    return LegQuery(
        leg=LEG_BM25,
        # $2 is the raw query text. $1 is the tenant id, bound by TenantScope.
        prelude=_LEXEME_OR_TSQUERY,
        joins="CROSS JOIN q",
        projection=f"ts_rank_cd(c.tsv, q.tsq, {_RANK_NORMALIZATION}) AS score",
        # The @@ match is what the GIN index on tsv actually serves. With an
        # OR-ed query this is a broad match, and ts_rank_cd does the real
        # work: it is a *cover density* ranker, so a chunk containing more of
        # the query's lexemes, closer together, scores higher. That is the
        # "soft AND" behavior we actually wanted all along.
        predicate="c.tsv @@ q.tsq",
        # c.id tiebreak: ties in ts_rank_cd are common (short chunks, same
        # term counts) and without a deterministic tiebreak the same eval run
        # produces different numbers on different days.
        order_by="score DESC, c.id",
        limit=limit,
        params=[query],
    )


async def search_bm25(
    scope: TenantScope, query: str, limit: int
) -> tuple[LegResult, dict[str, RetrievedChunk]]:
    """Run the keyword leg.

    Returns the observability record (what lands in a trace: ids, scores,
    timing, error) separately from the chunks themselves (working data the
    service needs but a trace should not carry — chunk text is large and
    already recoverable from chunk_id).
    """
    started = time.perf_counter()
    leg = build_bm25_leg(query, limit)

    try:
        rows = await scope.search(leg)
    except Exception as exc:  # noqa: BLE001 — one dead leg must not kill retrieval
        # Degrade to single-leg retrieval rather than failing the request.
        # The service records the degradation in RetrievalResult.degraded_legs
        # so it is visible in /stats, not just in a log nobody reads.
        logger.exception("bm25 leg failed for tenant %s", scope.tenant_id)
        return (
            LegResult(
                leg=LEG_BM25,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            ),
            {},
        )

    chunks: dict[str, RetrievedChunk] = {}
    chunk_ids: list[str] = []
    scores: dict[str, float] = {}
    for row in rows:
        chunk = row_to_chunk(row)
        chunks[chunk.chunk_id] = chunk
        chunk_ids.append(chunk.chunk_id)
        scores[chunk.chunk_id] = float(row["score"])

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if not chunk_ids:
        # With OR semantics this is now genuinely rare — it means the query
        # lexed to nothing (pure stopwords: "what about it?") or shares not a
        # single stem with any chunk in the tenant. Both are legitimate, so
        # this is INFO, not a warning. It was WARNING-worthy under the old AND
        # semantics, where it happened on most realistic queries.
        logger.info("bm25 leg matched nothing for query %r (tenant %s)", query, scope.tenant_id)

    return (
        LegResult(leg=LEG_BM25, chunk_ids=chunk_ids, scores=scores, elapsed_ms=elapsed_ms),
        chunks,
    )
