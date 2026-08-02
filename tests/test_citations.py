"""Citation parsing and post-hoc validation (Design.md §7).

Two halves, tested differently:

  * Parsing and claim splitting are pure text handling — exhaustively covered
    with plain assertions.
  * Validation needs embeddings, so it runs against FakeEncoder. That means
    these tests verify the MECHANICS (which claims got checked, which
    citations were flagged, how thresholds apply) and not semantic accuracy.
    FakeEncoder hashes text, so "similar text scores high" is not true for it
    and no test here may pretend otherwise. Semantic accuracy is Phase 4's
    job, with real embeddings and a labelled set.
"""

import datetime as dt

import pytest

from app.embeddings.service import EmbeddingService
from app.generation.citations import (
    CitationValidator,
    cosine_similarity,
    extract_markers,
    split_claims,
    strip_markers,
)
from app.generation.models import Citation


class StubEmbeddings(EmbeddingService):
    """Returns vectors we control, so similarity is scriptable.

    Subclasses the real service to guarantee the call signature stays honest —
    if `embed_passages` ever changes shape, this breaks rather than silently
    testing a different interface.
    """

    def __init__(self, similarity_by_text: dict[str, float] | None = None, default: float = 0.9):
        self.similarity_by_text = similarity_by_text or {}
        self.default = default
        self.calls = 0

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        # Build orthogonal-ish 2D vectors whose dot product equals the scripted
        # similarity. Chunk texts are the unit vector [1, 0]; each claim is
        # [s, sqrt(1-s^2)], so claim . chunk == s exactly.
        self.calls += 1
        vectors = []
        for text in texts:
            score = next(
                (s for key, s in self.similarity_by_text.items() if key in text), None
            )
            if score is None:
                score = 1.0 if text.startswith("CHUNK") else self.default
            if text.startswith("CHUNK"):
                vectors.append([1.0, 0.0])
            else:
                vectors.append([score, (1.0 - score**2) ** 0.5])
        return vectors


def citation(index: int) -> Citation:
    return Citation(
        index=index, chunk_id=f"chunk-{index}", document_id=f"doc-{index}",
        title=f"Doc {index}", source_type="docs", source_path=f"p{index}.md",
        effective_date=dt.date(2026, 1, 1),
    )


def chunks_for(*indices: int) -> dict[int, str]:
    return {i: f"CHUNK {i} body text" for i in indices}


# --------------------------------------------------------------- parsing --


def test_extract_markers_handles_every_shape():
    assert extract_markers("Retries cap at 5 [2].") == [2]
    assert extract_markers("Both agree [1][3].") == [1, 3]
    assert extract_markers("Combined [1, 2] form.") == [1, 2]
    assert extract_markers("No citations here.") == []


def test_markers_are_deduplicated_in_first_appearance_order():
    assert extract_markers("[2] then [1] then [2] again") == [2, 1]


def test_marker_regex_does_not_match_code_or_links():
    """Narrow on purpose: only digits inside brackets. A markdown link or an
    array index in a code sample must not become a phantom citation."""
    assert extract_markers("see [the docs](http://x)") == []
    assert extract_markers("items[0] and rows[i]") == []
    assert extract_markers("[ERR_TIMEOUT_502]") == []


def test_strip_markers_leaves_clean_prose():
    """Markers must not reach the embedder: they shift every claim's vector in
    the same direction, systematically biasing comparison against chunks
    (which contain no markers)."""
    assert strip_markers("Retries cap at 5 [2][3].") == "Retries cap at 5 ."


# ------------------------------------------------------- claim splitting --


def test_split_claims_on_sentences():
    answer = (
        "Retries are capped at five attempts [2]. The backoff is exponential [1]. "
        "Configure the schedule in project settings [1]."
    )
    assert len(split_claims(answer)) == 3


def test_split_claims_drops_fragments():
    """Short transitions are not factual claims. Demanding citations on them
    produces noise that teaches you to ignore the whole report."""
    claims = split_claims("Note: The retry limit was raised to five attempts in v2.4 [2].")
    assert all(len(claim) >= 25 for claim in claims)


def test_split_claims_does_not_break_on_version_numbers():
    """This corpus is full of 'v2.3' and '60 seconds'. Splitting inside them
    would fragment claims and make every similarity score meaningless."""
    claims = split_claims("The v2.3 release raised the timeout to 60.5 seconds for all plans [1].")
    assert len(claims) == 1


def test_split_claims_on_empty_answer():
    assert split_claims("") == []
    assert split_claims("   ") == []


# --------------------------------------------------------- cosine helper --


def test_cosine_similarity_edge_cases():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0  # mismatched dims


# ------------------------------------------------------------ validation --


async def test_fabricated_citation_index_is_flagged():
    """The unambiguous case: a marker pointing at a source that was never
    offered. Caught by parsing, needing no model at all — which is why the
    structural checks run before any embedding."""
    validator = CitationValidator(StubEmbeddings(), similarity_threshold=0.5)
    report, _ = await validator.validate(
        "Retries cap at 5 attempts per delivery [7].", [citation(1)], chunks_for(1)
    )
    assert report.invalid_indices == [7]
    assert report.has_fabricated_citations is True


async def test_valid_citations_are_not_flagged():
    validator = CitationValidator(StubEmbeddings(), similarity_threshold=0.5)
    report, _ = await validator.validate(
        "Retries cap at 5 attempts per delivery [1].",
        [citation(1), citation(2)], chunks_for(1, 2),
    )
    assert report.invalid_indices == []
    assert report.unused_indices == [2]


async def test_was_cited_is_set_on_each_source():
    """The UI greys out offered-but-unused sources, and Phase 4 uses this as a
    retrieval-precision signal."""
    citations = [citation(1), citation(2), citation(3)]
    validator = CitationValidator(StubEmbeddings(), similarity_threshold=0.5)
    await validator.validate(
        "The retry limit is five attempts in total [1][3].", citations, chunks_for(1, 2, 3)
    )
    assert [c.was_cited for c in citations] == [True, False, True]


async def test_uncited_sentence_is_marked_unsupported():
    """Prompt rule 1 forbids uncited claims, so one appearing is the strongest
    cheap evidence the model went outside its context."""
    validator = CitationValidator(StubEmbeddings(), similarity_threshold=0.5)
    report, _ = await validator.validate(
        "Retries cap at five attempts per delivery. The backoff is exponential [1].",
        [citation(1)], chunks_for(1),
    )
    problems = {check.problem for check in report.claims}
    assert "uncited" in problems
    assert len(report.unsupported_claims) == 1


async def test_weak_support_is_flagged_at_the_threshold():
    validator = CitationValidator(
        StubEmbeddings({"backoff": 0.2}, default=0.9), similarity_threshold=0.5
    )
    report, _ = await validator.validate(
        "The retry limit is five attempts total [1]. The backoff doubles each time [1].",
        [citation(1)], chunks_for(1),
    )
    weak = [check for check in report.claims if check.problem == "weak_support"]
    assert len(weak) == 1
    assert weak[0].similarity == pytest.approx(0.2)


async def test_a_claim_citing_two_sources_needs_only_one_to_support_it():
    """Rule 4 asks the model to cite BOTH sides of a conflict. Requiring every
    cited source to support the claim would punish exactly the behavior we
    asked for."""
    validator = CitationValidator(StubEmbeddings({"CLAIM": 0.9}), similarity_threshold=0.5)
    report, _ = await validator.validate(
        "CLAIM the retry limit is now five attempts [1][2].",
        [citation(1), citation(2)], chunks_for(1, 2),
    )
    assert report.claims[0].supported is True


ABSTENTION = (
    "I don't have enough information to answer this confidently. "
    "I'm escalating this to a human agent."
)


async def test_abstention_is_perfectly_grounded():
    """An abstention makes no factual claims, so grounding_rate is 1.0.

    If it scored 0.0, every correct abstention would drag the aggregate
    grounding metric down — a metric that punishes the safe behavior is worse
    than no metric. The pipeline routes abstentions away from validation
    anyway, but Phase 4 calls validate() directly, so the validator has to
    know this on its own.
    """
    validator = CitationValidator(
        StubEmbeddings(), similarity_threshold=0.5, abstention_message=ABSTENTION
    )
    report, _ = await validator.validate(ABSTENTION, [citation(1)], chunks_for(1))
    assert report.grounding_rate == 1.0
    assert report.unsupported_claims == []


async def test_abstention_detection_tolerates_model_decoration():
    """Models prepend "Unfortunately," and swap quote characters. Matching
    strictly would score a real abstention as an ungrounded claim."""
    validator = CitationValidator(
        StubEmbeddings(), similarity_threshold=0.5, abstention_message=ABSTENTION
    )
    report, _ = await validator.validate(
        "Unfortunately, I don’t have enough information to answer this confidently.",
        [citation(1)], chunks_for(1),
    )
    assert report.grounding_rate == 1.0


async def test_short_claim_with_a_citation_is_still_checked():
    """"Retries cap at 5 [2]." is 21 characters and unambiguously a factual
    claim — the model said so by citing it. Length is a heuristic for "is this
    a claim"; an explicit citation is evidence, and evidence beats a
    heuristic. Dropping it would let a whole class of short claims skip
    validation entirely."""
    claims = split_claims("Retries cap at 5 [2]. Backoff is exponential and capped [1].")
    assert len(claims) == 2
    assert claims[0] == "Retries cap at 5 [2]."


async def test_validation_costs_one_embedding_call_regardless_of_length():
    """Latency must not scale with how helpful the answer was — that is a
    perverse incentive. Claims and chunks are batched into one call."""
    embeddings = StubEmbeddings()
    validator = CitationValidator(embeddings, similarity_threshold=0.5)
    answer = " ".join(
        f"This is factual claim number {i} about the system [1]." for i in range(10)
    )
    await validator.validate(answer, [citation(1)], chunks_for(1))
    assert embeddings.calls == 1


async def test_disabled_validator_is_a_no_op():
    embeddings = StubEmbeddings()
    validator = CitationValidator(embeddings, enabled=False)
    report, elapsed = await validator.validate(
        "Retries cap at five attempts [9].", [citation(1)], chunks_for(1)
    )
    assert report.claims == [] and report.invalid_indices == []
    assert embeddings.calls == 0
    assert elapsed == 0
