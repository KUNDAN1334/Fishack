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


# THE MOST IMPORTANT LINE IN THIS FILE. It went through two wrong versions
# before this one, and both mistakes are instructive, so the reasoning stays.
#
# --- Attempt 1: websearch_to_tsquery as-is. Wrong: AND semantics. ---------
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
# --- Attempt 2: OR every lexeme. Fixes recall, loses identifier precision --
#
# Lexing with to_tsvector and joining lexemes with `|` fixed the zero-result
# problem. But running ts_debug on a real query shows what it cost:
#
#   to_tsvector('ERR_TIMEOUT_502')  ->  '502':3 'err':1 'timeout':2
#   parser tokens                   ->  ERR(asciiword) TIMEOUT(asciiword) 502(uint)
#
# The default parser treats `_` as a separator, so an identifier becomes three
# INDEPENDENT lexemes. A flat OR then matches a chunk containing merely "err"
# — and it did: a query for ERR_TIMEOUT_502 pulled an ERR_SCHEMA_MISMATCH
# ticket into BM25's top 5 on the strength of that one token. That is exactly
# the exact-identifier precision Design.md §5 says this leg exists to provide,
# thrown away.
#
# --- Attempt 3 (this one): OR across CONCEPTS, phrase within IDENTIFIERS ---
#
# The key observation is what websearch_to_tsquery does with a multi-token
# identifier. It does NOT use `&` there:
#
#   websearch_to_tsquery('ERR_TIMEOUT_502')  ->  'err' <-> 'timeout' <-> '502'
#
# `<->` is FOLLOWED-BY: it matches only where those lexemes appear adjacent,
# in order. That is true exact-identifier matching, and the parser hands it to
# us for free. So the two operators carry different meanings and deserve
# different treatment:
#
#   `&`    separates CONCEPTS the user typed  ->  should be OR (ranked retrieval)
#   `<->`  holds ONE identifier together      ->  must stay adjacent
#
# Replacing only ` & ` with ` | ` in the rendered tsquery leaves `<->` groups
# untouched, and tsquery precedence (`<->` binds tighter than `&`, which binds
# tighter than `|`) makes the result parse the way we want:
#
#   'webhook' & 'retri' & 'limit' & 'err' <-> 'timeout' <-> '502'
#      becomes
#   'webhook' | 'retri' | 'limit' | ('err' <-> 'timeout' <-> '502')
#
# A chunk mentioning only "err" no longer matches the identifier clause, while
# a chunk about webhooks still matches on one concept. Quoted phrases the user
# types ("rate limit") also render as `<->` and are preserved the same way.
#
# NULLIF guards the empty case: an all-stopword query renders as '', and
# ''::tsquery emits a NOTICE. NULL instead — `tsv @@ NULL` matches nothing.
#
# KNOWN LIMITATION: websearch's `-exclusion` renders as `!'term'`, and under OR
# semantics `a | !b` matches nearly everything. Support queries essentially
# never use it, so this is documented rather than handled. If it ever matters,
# detect `!` in the rendered text and fall back to the strict query.
#
# PRODUCTION NOTE: this is string surgery on a rendered tsquery, which is safe
# only because Postgres always quotes lexemes and pads operators with spaces.
# It is a solo-dev-scale trick. A real BM25 engine (OpenSearch/Vespa, or
# ParadeDB's pg_search) exposes per-clause operators directly and needs none
# of it.
_CONCEPT_OR_PHRASE_TSQUERY = """
WITH q AS (
    SELECT NULLIF(
        replace(websearch_to_tsquery('english', $2)::text, ' & ', ' | '),
        ''
    )::tsquery AS tsq
)
"""


def build_bm25_leg(query: str, limit: int) -> LegQuery:
    """Build the FTS leg fragment. Pure — no I/O, so it is directly testable.

    Two independent choices are baked in here:

    1. OR across concepts, phrase-adjacency within identifiers — see
       `_CONCEPT_OR_PHRASE_TSQUERY` above. This is what makes the leg a
       *ranked* retriever rather than a boolean filter, while keeping the
       exact-identifier precision that is the entire reason Design.md §5 wants
       a keyword leg at all.

    2. `websearch_to_tsquery` as the parser. Unlike `to_tsquery` it never
       raises on ordinary punctuation — a real support question ("why does
       POST /v2/events return 502?") must not 500 the endpoint — and unlike
       `plainto_tsquery` it emits `<->` for multi-token identifiers and
       user-typed quoted phrases, which is precisely the structure we want to
       preserve.

    The one thing given up is `-exclusion`, which is meaningless under OR
    semantics. Documented as a known limitation rather than handled.
    """
    return LegQuery(
        leg=LEG_BM25,
        # $2 is the raw query text. $1 is the tenant id, bound by TenantScope.
        prelude=_CONCEPT_OR_PHRASE_TSQUERY,
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
