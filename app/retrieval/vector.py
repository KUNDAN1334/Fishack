"""The semantic leg: cosine similarity over pgvector.

Design.md §5's other half. Where BM25 matches strings, this matches meaning:
a user who asks "why isn't my data syncing" finds a doc that says
"synchronization latency" — no shared words at all.

Two details that are easy to get wrong here:

1. `<=>` is cosine DISTANCE, not similarity. Similarity = 1 - distance. That
   identity is only valid because `app/embeddings/encoder.py` L2-normalizes
   every vector; on unnormalized vectors pgvector's cosine operator still
   works but the arithmetic below would be nonsense.

2. HNSW searches the graph FIRST and applies `WHERE tenant_id = ...` to
   whatever the graph returned. With a selective filter most of the beam is
   discarded, and you can get back fewer than `limit` rows with no error and
   no log — recall silently craters. Raising `hnsw.ef_search` widens the beam
   so more candidates survive the filter. This is the filtered-ANN problem
   documented in 001_init.sql and interview_prep Q6, and this module is where
   that documentation turns into code.

PRODUCTION NOTE: at real tenant counts the right fix is not a bigger beam but
a smaller graph — partition `chunks` by tenant, or use a vector DB with
native namespaces (Qdrant/Pinecone), so the index only ever contains one
tenant's vectors and the filter becomes free. Design.md §8 calls this the
namespace pattern; ef_search is the solo-dev-scale stand-in.
"""

from __future__ import annotations

import logging
import time

from app.retrieval.models import LEG_VECTOR, LegResult, RetrievedChunk
from app.retrieval.tenant_scope import LegQuery, TenantScope, row_to_chunk

logger = logging.getLogger(__name__)


def format_vector(vector: list[float]) -> str:
    """Python list -> pgvector literal, e.g. '[0.1,0.2,...]'.

    Same 7-decimal formatting as the ingestion side (repository.py,
    embeddings/service.py) on purpose: a query vector formatted differently
    from the stored vectors would introduce a tiny, invisible asymmetry in
    every distance computation.
    """
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def build_vector_leg(query_vector: list[float], limit: int, ef_search: int) -> LegQuery:
    """Build the pgvector leg fragment. Pure — no I/O.

    Note `$2::vector` appears twice (projection and ORDER BY). That is one
    bound parameter used twice, not two round trips; Postgres evaluates the
    distance once per row and reuses it.
    """
    literal = format_vector(query_vector)
    return LegQuery(
        leg=LEG_VECTOR,
        projection="1 - (c.embedding <=> $2::vector) AS score",
        # Chunks written before an embedding failure would otherwise sort as
        # NULL distance and pollute the top of the list.
        predicate="c.embedding IS NOT NULL",
        # Order by DISTANCE ascending — this is the expression the HNSW index
        # can serve. Ordering by `1 - distance` DESC is mathematically the
        # same ranking but Postgres would not recognize it as an index scan
        # and would fall back to a sequential scan over every chunk.
        order_by="c.embedding <=> $2::vector, c.id",
        limit=limit,
        params=[literal],
        local_settings={"hnsw.ef_search": ef_search},
    )


async def search_vector(
    scope: TenantScope, query_vector: list[float], limit: int, ef_search: int
) -> tuple[LegResult, dict[str, RetrievedChunk]]:
    """Run the semantic leg.

    The caller passes an already-embedded query. Embedding is not done here
    on purpose: hybrid retrieval embeds once and both the vector leg and
    (later) the semantic cache reuse that vector.
    """
    started = time.perf_counter()

    if not query_vector:
        # Defensive: an empty vector would make pgvector raise a dimension
        # error deep in SQL. Fail as a degraded leg instead, so BM25 can still
        # answer.
        logger.error("vector leg called with an empty query vector")
        return (
            LegResult(leg=LEG_VECTOR, error="empty query vector", elapsed_ms=0),
            {},
        )

    leg = build_vector_leg(query_vector, limit, ef_search)

    try:
        rows = await scope.search(leg)
    except Exception as exc:  # noqa: BLE001 — see bm25.py: degrade, don't die
        logger.exception("vector leg failed for tenant %s", scope.tenant_id)
        return (
            LegResult(
                leg=LEG_VECTOR,
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

    # The filtered-ANN symptom, made visible. Vector search always has SOME
    # nearest neighbor, so getting back fewer rows than asked for (when the
    # tenant plainly has more chunks than that) means the beam was too narrow
    # — the exact silent failure this module's docstring warns about.
    if len(chunk_ids) < limit:
        logger.info(
            "vector leg returned %d/%d rows (ef_search=%d) — expected when the tenant "
            "has few chunks, but a symptom of a too-narrow HNSW beam otherwise",
            len(chunk_ids), limit, ef_search,
        )

    return (
        LegResult(leg=LEG_VECTOR, chunk_ids=chunk_ids, scores=scores, elapsed_ms=elapsed_ms),
        chunks,
    )
