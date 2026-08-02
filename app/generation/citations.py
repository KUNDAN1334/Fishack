"""Citation parsing and post-hoc validation (Design.md §7).

    "After the LLM generates, run a quick check — for each citation marker,
     verify the cited chunk actually contains semantically similar content to
     catch 'fake citations'."

This is the third layer of the hallucination defense, and it is the only one
that inspects the *output*. The gate checks the inputs; the prompt shapes the
generation; this checks what came out. Design.md §7's closing line — no single
layer is reliable alone — is the whole argument for having all three.

What a "fake citation" actually looks like in practice, in rising order of how
hard it is to detect:

  1. `[7]` when only 5 sources were offered. Unambiguous fabrication, caught
     by parsing rather than by any model.
  2. A sentence with no marker at all. The prompt forbids it, so its presence
     means the model produced something it could not attribute.
  3. `[2]` on a claim that source 2 does not discuss. Caught by similarity.
  4. `[2]` on a claim source 2 CONTRADICTS. **Not caught here.** Similarity
     scores "retries are capped at 3" and "retries are capped at 5" as highly
     similar — they are about the same thing. Only entailment separates them.

That fourth case is a real, documented hole. Every name in this module says
`similarity`, never `entailment`, so the limitation is visible at each call
site rather than buried in a docstring nobody reads at 2am.

PRODUCTION NOTE: the fix is an NLI model (roberta-large-mnli or similar) or an
LLM judge scoring entailment per claim. Design.md §13a lists entailment as its
own hallucination signal precisely because similarity is not it. We use
similarity because it is free, local, deterministic, and adds ~30ms — and
because a check that runs on every answer beats a better check that gets
disabled for being slow.
"""

from __future__ import annotations

import logging
import re
import time

from app.embeddings.service import EmbeddingService
from app.generation.models import Citation, CitationReport, ClaimCheck

logger = logging.getLogger(__name__)

# Citation markers: [1], [2][3], [1, 2]. Two narrowings, both load-bearing:
#
#   - only digits inside the brackets, so `[ERR_TIMEOUT_502]` and a markdown
#     link `[the docs](url)` are not citations;
#   - `(?<!\w)` rejects a bracket glued to a word, so `items[0]` in a code
#     sample is not a citation while `[1][3]` still is (`]` is not a word
#     character, so the second marker in a pair survives).
#
# A false positive here is worse than a miss: it would make the validator
# report a fabricated citation for an answer that never cited anything, and
# a trust feature that cries wolf gets switched off.
CITATION_MARKER = re.compile(r"(?<!\w)\[(\d+(?:\s*,\s*\d+)*)\]")

# Sentence splitting on terminal punctuation followed by whitespace and a
# capital/digit. Not linguistically perfect, but a claim boundary being
# slightly wrong costs a slightly noisy report, whereas pulling in a full NLP
# dependency costs a build. The lookahead avoids splitting inside version
# numbers and decimals, which are everywhere in this corpus.
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# Sentences shorter than this are transitions ("Note:", "For example:") rather
# than factual claims, and demanding a citation on them produces noise that
# teaches you to ignore the report.
#
# BUT: a short sentence that CARRIES a citation marker is always kept, however
# short. "Retries cap at 5 [2]." is 21 characters and is unambiguously a
# factual claim — the model said so by citing it. Length is a heuristic for
# "is this a claim"; an explicit citation is evidence, and evidence beats a
# heuristic.
MIN_CLAIM_CHARS = 15


def extract_markers(text: str) -> list[int]:
    """Every citation index appearing in `text`, in order, deduplicated."""
    found: list[int] = []
    for match in CITATION_MARKER.finditer(text):
        for part in match.group(1).split(","):
            index = int(part.strip())
            if index not in found:
                found.append(index)
    return found


def strip_markers(text: str) -> str:
    """Remove citation markers so a claim can be embedded as prose.

    Necessary because "[1]" contributes nothing to meaning but does shift the
    embedding — and it shifts EVERY claim's embedding in the same direction,
    which would systematically bias the similarity comparison against chunks
    (which contain no markers).
    """
    return CITATION_MARKER.sub("", text).strip()


def split_claims(answer: str) -> list[str]:
    """Split an answer into sentence-level claims.

    Sentence granularity is a judgement call. Finer (clause-level) would
    localize a failure better but multiplies the number of embeddings and
    produces fragments too short to embed meaningfully. Coarser (paragraph)
    would let one unsupported sentence hide inside three supported ones.
    Design.md §13e wants sentence-to-source mapping for the UI's
    highlight-on-hover, so sentences it is.
    """
    cleaned = " ".join(answer.split())
    if not cleaned:
        return []
    claims = []
    for part in SENTENCE_BOUNDARY.split(cleaned):
        sentence = part.strip()
        if not sentence:
            continue
        # Keep it if it is substantial OR if it carries a citation — see the
        # note on MIN_CLAIM_CHARS.
        if len(sentence) >= MIN_CLAIM_CHARS or CITATION_MARKER.search(sentence):
            claims.append(sentence)
    return claims


class CitationValidator:
    def __init__(
        self,
        embeddings: EmbeddingService,
        *,
        similarity_threshold: float = 0.50,
        enabled: bool = True,
        abstention_message: str | None = None,
    ):
        self.embeddings = embeddings
        self.similarity_threshold = similarity_threshold
        self.enabled = enabled
        # The validator must recognize an abstention on its own. The pipeline
        # already routes abstentions away from validation, but Phase 4's eval
        # harness calls validate() directly on arbitrary answers — and
        # scoring "I don't have enough information" as an ungrounded claim
        # would make every correct abstention drag the grounding metric down.
        # A metric that punishes the safe behavior is worse than no metric.
        self.abstention_message = abstention_message

    async def validate(
        self,
        answer: str,
        citations: list[Citation],
        chunk_texts: dict[int, str],
    ) -> tuple[CitationReport, int]:
        """Check every claim in `answer` against the sources it cites.

        Args:
            answer: the generated text, markers intact.
            citations: the numbered sources offered to the model. Mutated —
                `was_cited` is set on each.
            chunk_texts: citation index -> the chunk body the model was shown.

        Returns:
            (report, elapsed_ms)
        """
        started = time.perf_counter()
        report = CitationReport()

        if not self.enabled:
            return report, 0

        if self._is_abstention(answer):
            # An abstention makes no factual claims, so it is perfectly
            # grounded by definition. Returning an empty report gives
            # grounding_rate == 1.0, which is the honest score.
            return report, 0

        claims = split_claims(answer)
        valid_indices = {citation.index for citation in citations}

        # ---- 1. Structural checks: no model, no embeddings, no cost. ----
        # Done first because a marker pointing at a source that does not exist
        # is unambiguous fabrication, and no similarity score can make it fine.
        all_markers = extract_markers(answer)
        report.invalid_indices = sorted(i for i in all_markers if i not in valid_indices)
        cited_indices = {i for i in all_markers if i in valid_indices}
        for citation in citations:
            citation.was_cited = citation.index in cited_indices
        report.unused_indices = sorted(valid_indices - cited_indices)

        if report.invalid_indices:
            logger.warning(
                "answer cites sources that were never offered: %s (offered 1..%d)",
                report.invalid_indices, len(citations),
            )

        if not claims:
            # An abstention, or a very short answer. Nothing to verify, and a
            # grounding_rate of 1.0 is correct — an abstention makes no
            # unsupported claims.
            return report, int((time.perf_counter() - started) * 1000)

        # ---- 2. Semantic check: one batched embedding call. ----
        # Claims and chunks are embedded together in ONE call so the whole
        # validation costs a single model invocation regardless of answer
        # length. Embedding per claim would make validation latency scale with
        # how helpful the answer was, which is a perverse incentive.
        claim_texts = [strip_markers(claim) for claim in claims]
        used_indices = sorted(cited_indices)
        texts_to_embed = claim_texts + [chunk_texts.get(i, "") for i in used_indices]
        vectors = await self.embeddings.embed_passages(texts_to_embed)

        claim_vectors = vectors[: len(claim_texts)]
        chunk_vectors = {
            index: vectors[len(claim_texts) + position]
            for position, index in enumerate(used_indices)
        }

        for claim_text, claim_vector in zip(claims, claim_vectors):
            check = ClaimCheck(claim=claim_text, cited_indices=extract_markers(claim_text))

            usable = [i for i in check.cited_indices if i in chunk_vectors]
            if not check.cited_indices:
                # Rule 1 violation: an uncited sentence. The prompt forbids it,
                # so its presence is the strongest cheap signal that the model
                # went outside its context (Design.md §7 technique 3).
                check.problem = "uncited"
            elif not usable:
                check.problem = "unknown_source"
            else:
                # Best match across everything this claim cited — a claim
                # citing [1][2] is supported if EITHER source backs it. The
                # alternative (requiring all) would punish correct multi-source
                # citations, which is the behavior we asked for in rule 4.
                check.similarity = max(
                    cosine_similarity(claim_vector, chunk_vectors[i]) for i in usable
                )
                check.supported = check.similarity >= self.similarity_threshold
                if not check.supported:
                    check.problem = "weak_support"

            report.claims.append(check)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if report.unsupported_claims:
            logger.info(
                "citation validation: %d/%d claims unsupported",
                len(report.unsupported_claims), report.total_claims,
            )
        return report, elapsed_ms


    def _is_abstention(self, answer: str) -> bool:
        """Reuses the generator's detector so the two can never disagree about
        what an abstention is — the same string appears in the prompt, the
        pipeline's action classification, and Phase 4's hard assertions."""
        if not self.abstention_message:
            return False
        from app.generation.generator import is_abstention

        return is_abstention(answer, self.abstention_message)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product — valid as cosine ONLY because both vectors are L2-normalized
    by `Encoder` (see app/embeddings/encoder.py). Written out rather than
    imported so the dependency on normalization is visible at the point where
    it matters."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
