"""Reciprocal Rank Fusion — merging the two legs (Design.md §5).

The problem: BM25 and vector search both produce ranked lists, but their
scores are not comparable. `ts_rank_cd` is unbounded and depends on term
frequencies in this corpus; cosine similarity is in [0, 1] and depends on the
query. "0.83" means something completely different in each. You cannot add
them, average them, or threshold them jointly.

The obvious fix — normalize both to 0-1 and take a weighted sum — is worse
than it looks. Min-max normalization over the returned window makes every
list's best result 1.0 and worst 0.0, which *destroys* the information that
one leg found nothing good: a leg whose top hit is garbage still contributes
a confident 1.0. Z-scores need a distribution you do not have. And whatever
you pick, the weights need retuning for every corpus.

RRF sidesteps all of it by throwing the scores away and using only RANK:

        score(d) = Σ over legs   weight_leg / (k + rank_leg(d))

Properties worth being able to state out loud in an interview:

  * Scale-free. No normalization step exists to get wrong.
  * Agreement is rewarded arithmetically, not by a special case. A chunk at
    rank 3 in BOTH legs scores 2/63 = 0.0317 and beats a chunk at rank 1 in
    one leg only (1/61 = 0.0164). That IS the hybrid benefit — it falls out
    of the sum rather than being coded.
  * k (default 60, from Cormack et al. 2009) damps the top of each list.
    At k=60, rank 1 (1/61) and rank 2 (1/62) differ by under 2%, so one leg
    being very confident cannot steamroll the other. Small k = winner-takes-
    all; large k = every rank nearly equal.
  * Bounded contribution. A leg can add at most weight/(k+1) per document, so
    a broken leg returning nonsense degrades the ranking gently instead of
    destroying it.

The cost, stated honestly: rank-only fusion is blind to MARGIN. If BM25's #1
is an exact error-code hit and its #2 is unrelated, RRF treats that gap the
same as a near-tie. Score-aware fusion could exploit it — at the price of the
normalization problem above. We take the trade, and Phase 4 measures it.

This module is pure: no database, no models, no config object, no I/O. It
takes lists of ids and returns fused ids. That is what makes it the one piece
of the retrieval pipeline you can unit-test to exhaustion in milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Cormack, Clarke & Buettcher (2009), "Reciprocal Rank Fusion Outperforms
# Condorcet and Individual Rank Learning Methods". 60 is their empirical
# choice and has been the field default ever since.
DEFAULT_RRF_K = 60.0


@dataclass
class FusedCandidate:
    """One document's fusion outcome, with the evidence that produced it.

    `contributions` is kept so the playground can show WHY something ranked
    where it did, and so a failing eval case can be explained without
    re-running retrieval. Debuggability is not free, but it is cheap here.
    """

    chunk_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)          # leg -> rank
    contributions: dict[str, float] = field(default_factory=dict)  # leg -> w/(k+rank)

    @property
    def leg_count(self) -> int:
        """How many legs found this document. 2 = both agreed."""
        return len(self.ranks)

    @property
    def best_rank(self) -> int:
        """Best position across all legs — the tiebreak below."""
        return min(self.ranks.values()) if self.ranks else 10**9


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]],
    *,
    k: float = DEFAULT_RRF_K,
    weights: dict[str, float] | None = None,
    top_k: int | None = None,
) -> list[FusedCandidate]:
    """Merge ranked id lists into one ranking.

    Args:
        ranked_lists: leg name -> ids ordered best-first. Duplicate ids within
            one list are ignored after their first (best) occurrence; a leg
            should not return duplicates, and if it does, its BEST opinion is
            the one that counts.
        k: rank-damping constant. Must be > 0 — at k=0 a rank-1 document would
            score 1/1 while rank 2 scores 1/2, i.e. winner-takes-all, which is
            the behavior RRF exists to avoid.
        weights: leg name -> multiplier. Missing legs default to 1.0.
        top_k: truncate the output. None returns everything.

    Returns:
        Candidates sorted best-first, deterministically.

    Determinism matters more than it looks: eval metrics computed on a
    ranking that reshuffles ties between runs are not reproducible, and you
    end up chasing "regressions" that are just dict ordering. The sort key is
    therefore total (score, then agreement, then best rank, then id).
    """
    if k <= 0:
        raise ValueError(f"RRF k must be positive, got {k}. See the module docstring.")

    weights = weights or {}
    fused: dict[str, FusedCandidate] = {}

    for leg, chunk_ids in ranked_lists.items():
        weight = weights.get(leg, 1.0)
        if weight == 0:
            # An explicitly zero-weighted leg contributes nothing. Skipping it
            # entirely (rather than adding 0.0) keeps `ranks` honest: the leg
            # did not influence the outcome, so it should not appear as
            # evidence in the playground or a trace.
            continue

        for position, chunk_id in enumerate(chunk_ids, start=1):
            candidate = fused.get(chunk_id)
            if candidate is None:
                candidate = FusedCandidate(chunk_id=chunk_id, score=0.0)
                fused[chunk_id] = candidate
            elif leg in candidate.ranks:
                continue  # duplicate within one list: keep the better rank

            contribution = weight / (k + position)
            candidate.score += contribution
            candidate.ranks[leg] = position
            candidate.contributions[leg] = contribution

    ordered = sorted(
        fused.values(),
        key=lambda candidate: (
            -candidate.score,      # primary: fused score, descending
            -candidate.leg_count,  # ties: prefer the doc both legs found
            candidate.best_rank,   # then: whoever ranked higher somewhere
            candidate.chunk_id,    # last resort: stable, arbitrary, total
        ),
    )
    return ordered[:top_k] if top_k is not None else ordered
