"""Cross-encoder reranking (Design.md §6).

Why a second scoring pass at all. The first-stage retrievers are *bi-encoders*
in spirit: BM25 and the vector leg both score the query and the document
INDEPENDENTLY (a tsvector and a 384-dim vector, computed without ever seeing
each other) and compare the results. That independence is what makes them
fast — every chunk is embedded once at ingestion time and indexed. It is also
what makes them approximate: the model never gets to ask "does this passage
answer THIS question?", only "are these two things in the same region of
space?".

A *cross-encoder* concatenates query and passage into one input and runs full
attention across both. It can notice that the passage mentions the right error
code in the wrong context, or that it answers a superficially similar question
about a different product area. That is dramatically more accurate — and
dramatically more expensive, because it is one forward pass per (query,
passage) PAIR, with nothing precomputable. You cannot index it. That is the
whole reason for the two-stage funnel: retrieve 20 cheaply, rescore 20
expensively, send 5 to the LLM.

The scoring subtlety that silently breaks thresholds: bge-reranker-base emits
a raw LOGIT, roughly in the range -11..+11, not a probability. Its absolute
value has no fixed meaning, and it is not comparable to the 0-1 scores every
other stage produces. We therefore apply a sigmoid and keep BOTH numbers —
`rerank_score` (0-1, what Phase 3's confidence gate thresholds on) and
`rerank_score_raw` (the logit, for debugging and for anyone who wants to see
the model's actual output). Thresholding a logit directly is the kind of bug
that produces a confidence gate that never fires.

PRODUCTION NOTE: Cohere Rerank / a hosted bge-reranker-large on GPU would be
the paid choice — normalized relevance scores out of the box, ~10x the
throughput, no 300MB model in the API process. The interface below would not
change; only the `Reranker` implementation would.
"""

from __future__ import annotations

import logging
import math
import time
from functools import lru_cache
from typing import Protocol, Sequence

from app.retrieval.models import ScoredChunk

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """Interface the service depends on.

    A Protocol rather than a base class so tests can pass a plain object with
    a `score_pairs` method and never import torch — the same trick
    `ApproxTokenCounter` plays for the chunkers (ADR-010). Keeping the whole
    unit suite torch-free is worth a small amount of indirection.
    """

    def score_pairs(self, query: str, passages: Sequence[str]) -> list[float]:
        """Return one RAW score (logit) per passage, in the input order."""


def sigmoid(logit: float) -> float:
    """Map a logit to (0, 1).

    Written out rather than pulled from torch/scipy because it is three lines
    and this file should be readable without a numerical-computing background.

    The branch avoids `exp` overflow: for a large negative logit, `exp(-x)`
    would overflow to inf. Mathematically the two branches are identical.
    """
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp_logit = math.exp(logit)
    return exp_logit / (1.0 + exp_logit)


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder wrapper (BAAI/bge-reranker-base)."""

    def __init__(self, model_name: str, batch_size: int = 16, max_length: int = 512):
        from sentence_transformers import CrossEncoder  # lazy: heavy import

        logger.info("loading reranker %s (first run downloads ~280MB)", model_name)
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        # max_length covers query + passage TOGETHER. Chunks average ~200
        # tokens so 512 rarely binds, but silent truncation here would score
        # a passage the model only half-read — so we set it explicitly and
        # warn below rather than relying on a library default.
        self.model = CrossEncoder(model_name, max_length=max_length)

    def score_pairs(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, passage) for passage in passages]
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [float(score) for score in scores]


@lru_cache
def get_reranker(model_name: str, batch_size: int = 16, max_length: int = 512) -> CrossEncoderReranker:
    """Process-wide singleton — loading the model costs seconds and ~300MB of
    RAM. Same pattern as `get_encoder`."""
    return CrossEncoderReranker(model_name, batch_size, max_length)


def rerank_candidates(
    reranker: Reranker,
    query: str,
    candidates: list[ScoredChunk],
    *,
    top_k: int,
    max_length: int = 512,
) -> tuple[list[ScoredChunk], int]:
    """Rescore candidates with the cross-encoder and return the best `top_k`.

    Mutates the ScoredChunk objects in place (setting rerank_* fields) and
    returns a new sorted list. Mutating is deliberate: the caller keeps the
    FULL candidate list with rerank scores attached, which is what makes
    "the reranker demoted the correct chunk from 2 to 14" a diagnosable
    statement in Phase 4 rather than a guess.

    Returns:
        (top_k results best-first, elapsed milliseconds)
    """
    if not candidates:
        return [], 0

    started = time.perf_counter()

    # A crude pre-check for the truncation problem. The cross-encoder's limit
    # is in TOKENS and this counts characters, so ~4 chars/token is the usual
    # rule of thumb; we only want a loud hint, not an exact measurement.
    approx_limit_chars = max_length * 4
    oversized = sum(1 for c in candidates if len(c.chunk.content) + len(query) > approx_limit_chars)
    if oversized:
        logger.warning(
            "%d/%d candidates may exceed the reranker's %d-token window and will be "
            "truncated — their scores reflect only the beginning of the passage",
            oversized, len(candidates), max_length,
        )

    raw_scores = reranker.score_pairs(query, [c.chunk.content for c in candidates])

    if len(raw_scores) != len(candidates):
        # A reranker that returns the wrong number of scores would silently
        # misalign scores with chunks — every answer would cite the wrong
        # sources while looking perfectly healthy. Refuse.
        raise ValueError(
            f"reranker returned {len(raw_scores)} scores for {len(candidates)} candidates"
        )

    for candidate, raw in zip(candidates, raw_scores):
        candidate.rerank_score_raw = raw
        candidate.rerank_score = sigmoid(raw)

    # Sort on the raw logit: sigmoid is monotonic so the order is identical,
    # but sorting on the pre-squash value avoids ties introduced by floating
    # point saturation at the extremes (sigmoid(12) and sigmoid(14) both
    # round to 1.0 in float64's practical precision for our purposes).
    ordered = sorted(
        candidates,
        key=lambda c: (-(c.rerank_score_raw or 0.0), c.chunk.chunk_id),
    )
    for position, candidate in enumerate(ordered, start=1):
        candidate.rerank_rank = position

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "reranked %d candidates in %dms (top score %.3f)",
        len(candidates), elapsed_ms, ordered[0].rerank_score or 0.0,
    )
    return ordered[:top_k], elapsed_ms
