"""LLM-as-judge for generation quality (Design.md §12).

Retrieval metrics are arithmetic over id lists. Generation quality is not:
there is no string-matching definition of "is this answer faithful to its
sources". So a stronger model reads the answer, the context it was given, and
a reference answer, and scores it against an explicit rubric.

WHY A DIFFERENT MODEL FROM THE GENERATOR (ADR-020). A model judging its own
output shares its blind spots. If the generator misreads a chunk, the same
model asked "is this faithful?" tends to misread it the same way and answer
yes. The failures are correlated, so the judge is measuring agreement with
itself rather than correctness. We generate with `llama-3.1-8b-instant` and
judge with `llama-3.3-70b-versatile` — a different model AND a different size
class, which is the direction that matters: the judge should be the stronger
of the two, or it is being asked to grade work above its level.

WHY THE RUBRIC IS EXPLICIT AND VISIBLE. "Rate this answer 1-10" produces
numbers that drift between runs and cannot be reasoned about. A rubric with
named criteria, a 0-1 scale per criterion, and stated anchor points is
reproducible enough to diff across runs — and, more importantly, is
inspectable. When a score looks wrong you can read the rubric and see whether
the judge or the rubric was at fault. The prompt lives here as a module
constant, in one place, so there is no second copy to drift out of sync.

WHAT LLM-AS-JUDGE IS NOT. It is a noisy estimator, not a measurement. The
same answer can score differently on consecutive judgements, which is exactly
why the CI regression gate tolerates a 5% drop on judge metrics while
tolerating ZERO on hard assertions (ADR-022). Treat judge scores as a trend
line and the hard assertions as a gate.
"""

from __future__ import annotations

import json
import logging
import re

from app.llm.base import ChatMessage
from app.llm.client import LLMClient
from fishnet.models import JudgeScores

logger = logging.getLogger(__name__)

# The rubric, verbatim and in exactly one place. A scorecard whose rubric is
# hidden cannot be argued with, so this constant IS the documentation.
JUDGE_SYSTEM_PROMPT = """You are evaluating a customer support assistant's answer. You are strict, literal, and you do not give credit for plausible-sounding text.

You will be given:
  CONTEXT   the numbered sources the assistant was shown
  QUESTION  what the user asked
  ANSWER    what the assistant produced
  REFERENCE a known-good answer, for comparison

Score three criteria from 0.0 to 1.0.

1. FAITHFULNESS — is every factual claim in ANSWER supported by CONTEXT?
   1.0  every claim traceable to the context
   0.5  mostly supported, but at least one claim goes beyond it
   0.0  contains claims the context does not support at all
   Judge only against CONTEXT, never against your own knowledge. A claim that
   is true in the real world but absent from the context scores 0.

2. CITATION_ACCURACY — does each [n] marker point at a source that actually
   supports the claim it is attached to?
   1.0  every marker supports its claim
   0.5  some markers are attached to the wrong source
   0.0  markers are decorative or point at unrelated sources
   A claim with no marker at all counts against this score.

3. ANSWER_RELEVANCE — does ANSWER address the QUESTION that was asked?
   1.0  directly answers it
   0.5  partially, or answers a related question
   0.0  does not address it
   An abstention ("I don't have enough information") scores 1.0 when the
   context genuinely does not contain the answer, and 0.0 when it does.

RULES:
- Score against CONTEXT and REFERENCE only. Never use outside knowledge.
- A shorter answer is not worse. Do not reward length or hedging.
- If sources conflict and ANSWER follows the more recent one AND says the
  older one disagrees, that is full marks on faithfulness — it is the
  behaviour the system is designed for, not a contradiction.

Respond with ONLY a JSON object, no prose before or after:
{"faithfulness": 0.0, "citation_accuracy": 0.0, "answer_relevance": 0.0, "reasoning": "one or two sentences"}"""


def build_judge_messages(
    question: str, context: str, answer: str, reference: str
) -> list[ChatMessage]:
    """Assemble the judging call.

    REFERENCE goes last, immediately before the model answers. Placed early it
    gets anchored on and the judge scores similarity-to-reference rather than
    faithfulness-to-context — which would reward paraphrasing the reference
    over actually being grounded.
    """
    return [
        ChatMessage(role="system", content=JUDGE_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=(
                f"CONTEXT:\n{context}\n\n"
                f"QUESTION:\n{question}\n\n"
                f"ANSWER:\n{answer}\n\n"
                f"REFERENCE (a known-good answer):\n{reference or '(none provided)'}\n\n"
                "JSON:"
            ),
        ),
    ]


def parse_judge_response(text: str) -> dict | None:
    """Extract the JSON verdict from the judge's reply.

    Models wrap JSON in prose and markdown fences despite being told not to,
    so we find the first balanced object rather than parsing the whole reply.
    Returns None on failure, which the caller records as `skipped` — a parse
    failure must never become a score of 0.0, or a flaky judge would look like
    a quality regression.
    """
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clamp(value) -> float | None:
    """Judges occasionally return 1-10, or a string, or 95. Coerce into 0-1
    and clamp; anything unparseable becomes None (not measured)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0:
        # A judge answering on a 0-10 or 0-100 scale despite the rubric.
        number = number / 10.0 if number <= 10.0 else number / 100.0
    return max(0.0, min(1.0, number))


class Judge:
    def __init__(self, llm: LLMClient, model_name: str = ""):
        self.llm = llm
        # Recorded on every score and in the report header. Judge scores from
        # different models are not comparable, and a report that does not say
        # which model produced them cannot be diffed against another.
        self.model_name = model_name

    async def score(
        self, *, question: str, context: str, answer: str, reference: str = ""
    ) -> JudgeScores:
        """Judge one answer. Never raises — a dead judge must not kill a run
        that has already produced valid retrieval metrics."""
        if not answer.strip():
            return JudgeScores(skipped=True, skip_reason="empty answer",
                               judge_model=self.model_name)

        try:
            response = await self.llm.complete(
                build_judge_messages(question, context, answer, reference),
                # Temperature 0: judging must be as reproducible as the
                # provider allows. Any sampling here shows up as run-to-run
                # noise that the regression gate would read as a regression.
                temperature=0.0,
                max_tokens=400,
            )
        except Exception as exc:  # noqa: BLE001 — quota exhaustion is expected
            logger.warning("judge call failed: %s", exc)
            return JudgeScores(
                skipped=True, skip_reason=f"{type(exc).__name__}: {exc}",
                judge_model=self.model_name,
            )

        parsed = parse_judge_response(response.text)
        if parsed is None:
            logger.warning("could not parse judge output: %r", response.text[:200])
            return JudgeScores(
                skipped=True, skip_reason="unparseable judge output",
                judge_model=response.model or self.model_name,
            )

        return JudgeScores(
            faithfulness=_clamp(parsed.get("faithfulness")),
            citation_accuracy=_clamp(parsed.get("citation_accuracy")),
            answer_relevance=_clamp(parsed.get("answer_relevance")),
            reasoning=str(parsed.get("reasoning", ""))[:500],
            judge_model=response.model or self.model_name,
        )
