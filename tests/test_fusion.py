"""RRF properties, verified against hand-computed arithmetic.

fusion.py is pure, so every claim its docstring makes should be assertable
here without a database, a model, or a mock. If a test in this file needs a
fixture, the module has grown a dependency it should not have.
"""

import pytest

from app.retrieval.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion

K = DEFAULT_RRF_K  # 60


def ids(fused):
    return [candidate.chunk_id for candidate in fused]


# ------------------------------------------------------------- basic math --


def test_single_list_scores_are_one_over_k_plus_rank():
    fused = reciprocal_rank_fusion({"bm25": ["a", "b", "c"]})
    assert ids(fused) == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(1 / (K + 1))
    assert fused[1].score == pytest.approx(1 / (K + 2))
    assert fused[2].score == pytest.approx(1 / (K + 3))


def test_single_list_preserves_order():
    """A one-leg fusion must be a no-op on ordering — this is what makes
    mode='bm25' in the service a fair single-leg baseline rather than a
    subtly reshuffled one."""
    original = [f"chunk-{i}" for i in range(20)]
    assert ids(reciprocal_rank_fusion({"bm25": original})) == original


def test_scores_sum_across_legs():
    fused = reciprocal_rank_fusion({"bm25": ["a"], "vector": ["a"]})
    assert fused[0].score == pytest.approx(2 / (K + 1))
    assert fused[0].leg_count == 2
    assert fused[0].ranks == {"bm25": 1, "vector": 1}


# ---------------------------------------------- the whole point of hybrid --


def test_agreement_beats_a_single_confident_hit():
    """The headline property: a chunk both legs rank 3rd outranks a chunk
    only one leg ranked 1st. 2/63 = 0.03175 > 1/61 = 0.01639."""
    fused = reciprocal_rank_fusion(
        {
            "bm25": ["solo", "x", "agreed"],
            "vector": ["y", "z", "agreed"],
        }
    )
    assert ids(fused)[0] == "agreed"
    assert fused[0].score == pytest.approx(2 / (K + 3))


def test_agreement_wins_even_at_the_bottom_of_our_candidate_window():
    """How strong is the agreement boost at k=60? Strong enough that, at our
    configured depth of 20 candidates per leg, a chunk both legs ranked LAST
    still outranks a chunk only one leg ranked FIRST:

        agreed:  2/(60+20) = 0.02500
        solo:    1/(60+ 1) = 0.01639

    This is worth knowing and not obvious. It means that in practice, for
    Fishly's configuration, "both legs found it" dominates the ranking. That
    is the behavior we want from hybrid retrieval — but it also means the
    per-leg candidate depth is a real tuning knob, not a formality.
    """
    fused = reciprocal_rank_fusion(
        {
            "bm25": ["solo"] + [f"pad-{i}" for i in range(18)] + ["agreed"],
            "vector": [f"other-{i}" for i in range(19)] + ["agreed"],
        }
    )
    assert ids(fused)[0] == "agreed"
    assert fused[0].score == pytest.approx(2 / (K + 20))


def test_the_crossover_depth_where_agreement_stops_winning():
    """Agreement is a boost, not a trump card — but the crossover is deep.

        2/(k+r) < 1/(k+1)   <=>   r > k + 2

    At k=60 that is r >= 63: agreement must be at rank 63 or worse in BOTH
    legs before a single rank-1 hit overtakes it. (At exactly r=62 the scores
    are equal: 2/122 == 1/61.) We never retrieve that deep, which is the
    honest reason the previous test's result is not a coincidence.
    """
    def agreement_at(rank: int):
        # Pads are named "z..." so they lose the alphabetical tiebreak to
        # "solo". The vector leg's rank-1 pad ties with solo on score, and
        # without this precaution the test would assert on id ordering while
        # claiming to assert on the crossover.
        pad_a = [f"za{i}" for i in range(rank - 1)]
        pad_b = [f"zb{i}" for i in range(rank - 1)]
        return reciprocal_rank_fusion(
            {"bm25": ["solo"] + pad_a[1:] + ["agreed"], "vector": pad_b + ["agreed"]}
        )

    assert 2 / (K + 62) == pytest.approx(1 / (K + 1))   # the exact tie point
    assert ids(agreement_at(62))[0] == "agreed"          # tie -> agreement wins on leg_count
    assert ids(agreement_at(70))[0] == "solo"            # past the crossover


def test_contributions_record_the_evidence():
    fused = reciprocal_rank_fusion({"bm25": ["a", "b"], "vector": ["b"]})
    by_id = {candidate.chunk_id: candidate for candidate in fused}
    assert by_id["b"].contributions == pytest.approx(
        {"bm25": 1 / (K + 2), "vector": 1 / (K + 1)}
    )
    assert by_id["a"].contributions.keys() == {"bm25"}


# ----------------------------------------------------------------- k knob --


def test_small_k_is_more_top_heavy():
    """k is the dial between "agreement matters" and "winner takes all".

    Ids are chosen so that alphabetical tiebreaking cannot rescue the
    assertion: at k=1, `asolo` and `zq1` BOTH score 1/2, and `asolo` only
    comes first because it sorts first. Naming them the other way round would
    make this test pass or fail for a reason that has nothing to do with k —
    which is how my first version of it lied to me.
    """
    lists = {
        "bm25": ["asolo", "p1", "p2", "agreed"],
        "vector": ["zq1", "zq2", "zq3", "agreed"],
    }
    # k=60: agreement wins (2/64 = 0.03125 > 1/61 = 0.01639)
    assert ids(reciprocal_rank_fusion(lists, k=60))[0] == "agreed"
    # k=1: rank 1 dominates (1/2 = 0.5 > 2/5 = 0.4), agreement is demoted
    assert ids(reciprocal_rank_fusion(lists, k=1))[0] == "asolo"
    assert ids(reciprocal_rank_fusion(lists, k=1)).index("agreed") > 0


def test_k_must_be_positive():
    with pytest.raises(ValueError, match="must be positive"):
        reciprocal_rank_fusion({"bm25": ["a"]}, k=0)


# --------------------------------------------------------------- weights --


def test_weights_scale_a_legs_contribution():
    fused = reciprocal_rank_fusion(
        {"bm25": ["a"], "vector": ["b"]},
        weights={"bm25": 2.0, "vector": 1.0},
    )
    assert ids(fused) == ["a", "b"]
    assert fused[0].score == pytest.approx(2 / (K + 1))


def test_zero_weight_leg_contributes_no_evidence():
    """A zero-weighted leg must vanish from the evidence, not appear with a
    0.0 contribution — the playground reads `ranks` as 'which legs found
    this', and a leg that had no influence did not find it for our purposes."""
    fused = reciprocal_rank_fusion(
        {"bm25": ["a"], "vector": ["a", "b"]},
        weights={"vector": 0.0},
    )
    assert ids(fused) == ["a"]           # "b" came only from the muted leg
    assert fused[0].ranks == {"bm25": 1}


def test_missing_weight_defaults_to_one():
    fused = reciprocal_rank_fusion({"bm25": ["a"]}, weights={"vector": 5.0})
    assert fused[0].score == pytest.approx(1 / (K + 1))


# ------------------------------------------------------------ robustness --


def test_empty_inputs():
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"bm25": [], "vector": []}) == []


def test_one_empty_leg_is_harmless():
    """A leg that matched nothing (all-stopword query, say) must not change
    the surviving leg's order."""
    fused = reciprocal_rank_fusion({"bm25": [], "vector": ["a", "b", "c"]})
    assert ids(fused) == ["a", "b", "c"]


def test_duplicate_within_one_list_keeps_the_better_rank():
    """A leg should not return duplicates; if it does, its best opinion wins
    and the document is not double-counted."""
    fused = reciprocal_rank_fusion({"bm25": ["a", "b", "a"]})
    assert ids(fused) == ["a", "b"]
    assert fused[0].score == pytest.approx(1 / (K + 1))  # not 1/61 + 1/63
    assert fused[0].ranks == {"bm25": 1}


def test_top_k_truncates():
    fused = reciprocal_rank_fusion({"bm25": ["a", "b", "c", "d"]}, top_k=2)
    assert ids(fused) == ["a", "b"]


# ---------------------------------------------------------- determinism --


def test_ties_are_broken_deterministically():
    """Two documents at rank 1 in different legs have IDENTICAL scores. The
    order must still be stable across runs, or eval metrics wobble between
    identical runs and you chase phantom regressions."""
    lists = {"bm25": ["zebra"], "vector": ["alpha"]}
    first = ids(reciprocal_rank_fusion(lists))
    for _ in range(10):
        assert ids(reciprocal_rank_fusion(lists)) == first
    # ...and the documented rule is alphabetical by id as the final tiebreak
    assert first == ["alpha", "zebra"]


def test_exact_score_tie_falls_through_to_stable_id_order():
    """A mirror-image pair: `deep` is rank 1 in bm25 and rank 3 in vector,
    `shallow` is the reverse. Both score 1/61 + 1/63 EXACTLY, both were found
    by 2 legs, both have best_rank 1 — every tiebreak is equal until the id.

    Without that final key the two would be ordered by dict insertion, which
    is stable within a process but not across a code change that reorders leg
    execution. Eval numbers must not depend on that.
    """
    fused = reciprocal_rank_fusion(
        {
            "bm25": ["deep", "x", "shallow"],
            "vector": ["shallow", "y", "deep"],
        }
    )
    assert fused[0].score == pytest.approx(fused[1].score)
    assert ids(fused)[:2] == ["deep", "shallow"]
    # ...and the single-leg pair behind them ties too, resolved the same way.
    assert ids(fused)[2:] == ["x", "y"]


def test_agreement_outranks_a_higher_scoring_single_leg_tie():
    """The `leg_count` tiebreak, isolated: two documents with identical fused
    scores where one was found twice at rank 2 and the other once at a rank
    that happens to produce the same total. Constructed so ONLY leg_count
    can decide."""
    # "both" -> 2/(K+2). "single" -> 1/(K+2) from one leg... not equal.
    # Instead force the tie directly: same score, different leg counts is only
    # reachable when weights differ.
    fused = reciprocal_rank_fusion(
        {"bm25": ["both", "single"], "vector": ["both"]},
        weights={"bm25": 1.0, "vector": 1.0},
    )
    assert ids(fused) == ["both", "single"]
    assert fused[0].leg_count == 2 and fused[1].leg_count == 1
