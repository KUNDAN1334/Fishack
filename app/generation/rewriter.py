"""Multi-turn query rewriting (Design.md §2 step 2).

The problem it solves: retrieval has no memory. A user asks "why is my webhook
failing after the v2.3 update?", gets an answer, then asks "what about the
retry logic?". Embedding that four-word follow-up produces a vector near
generic retry documentation, and BM25 matches "retry" and "logic" everywhere.
The webhook context — the thing that makes the question answerable — is in the
previous turn, which the retriever never sees.

So we resolve the follow-up into a standalone question *before* retrieval:
"What is the retry logic for webhook failures after the v2.3 update?"

Design.md calls this out as the step people skip, and it is: it costs an extra
LLM call and it looks optional right up until you test a real conversation.

Three engineering decisions worth understanding:

1. SKIPPED ON THE FIRST TURN. A question with no conversation behind it is
   already standalone; rewriting can only paraphrase it, at the cost of a
   round trip and a chance to mangle an error code. Most support sessions are
   one turn, so this is not a micro-optimization.

2. FAILURE IS NEVER FATAL. If the rewrite call fails, times out, or returns
   something suspicious, we fall back to the raw query and record why. A
   degraded rewrite gives worse retrieval; a raised exception gives no answer
   at all. Design.md's whole thesis is that abstaining beats hallucinating —
   but neither beats simply answering the un-rewritten question.

3. THE OUTPUT IS VALIDATED. The dominant failure of a rewriting prompt is that
   the model ANSWERS the question instead of rewriting it, and an answer
   silently substituted for a query is a spectacular retrieval bug: you would
   be searching your corpus for the text of a hallucinated response. The
   length and shape checks below exist for that.
"""

from __future__ import annotations

import logging
import time

from app.generation.models import RewriteResult, Turn
from app.generation.prompts import build_rewrite_messages
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

# A rewritten question is a question. These caps are deliberately generous —
# they are catching "the model wrote a paragraph of answer", not policing
# style.
MAX_REWRITE_CHARS = 400
# If the model returns something far longer than the original AND long in
# absolute terms, it is answering rather than rewriting.
MAX_GROWTH_FACTOR = 6.0


def looks_like_a_rewrite(original: str, candidate: str) -> tuple[bool, str]:
    """Sanity-check the model's output before trusting it as a search query.

    Pure function so every rejection rule is directly testable — and these
    rules matter more than they look. A bad rewrite does not error; it
    quietly retrieves the wrong thing, and you would debug the retriever.
    """
    if not candidate:
        return False, "empty"
    if len(candidate) > MAX_REWRITE_CHARS:
        return False, "too_long"
    if len(candidate) > len(original) * MAX_GROWTH_FACTOR and len(candidate) > 200:
        return False, "grew_too_much"
    # Models that slip into answering often open with a refusal or a preamble.
    lowered = candidate.lower()
    for opener in ("i don't have enough information", "i'm escalating", "sure,", "here is"):
        if lowered.startswith(opener):
            return False, "looks_like_an_answer"
    # Multi-paragraph output is prose, not a query.
    if candidate.count("\n\n") >= 1:
        return False, "multi_paragraph"
    return True, "ok"


def clean_rewrite(raw: str) -> str:
    """Strip the decorations models add despite being told not to.

    Cheaper and more reliable than another prompt iteration: instruction-tuned
    models wrap short outputs in quotes or prefix them with a label often
    enough that handling it in code is simply correct.
    """
    text = raw.strip()
    for prefix in ("STANDALONE QUESTION:", "Standalone question:", "Question:", "Rewritten:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    # Balanced surrounding quotes only — an unbalanced quote is part of the
    # user's actual text and must survive.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text.strip()


class QueryRewriter:
    def __init__(
        self,
        llm: LLMClient,
        *,
        enabled: bool = True,
        history_turns: int = 6,
        max_tokens: int = 120,
    ):
        self.llm = llm
        self.enabled = enabled
        self.history_turns = history_turns
        self.max_tokens = max_tokens

    async def rewrite(self, query: str, history: list[Turn]) -> RewriteResult:
        """Resolve `query` into a standalone question, or return it unchanged."""
        if not self.enabled:
            return RewriteResult(original=query, rewritten=query, skipped_reason="disabled")

        if not history:
            # The common case, and free. A first-turn question is standalone
            # by definition.
            return RewriteResult(original=query, rewritten=query, skipped_reason="first_turn")

        started = time.perf_counter()
        # Most recent N turns. Older context is usually about a different
        # problem, and including it makes the rewriter drag stale entities
        # into the query — a subtler failure than truncating too aggressively.
        recent = history[-self.history_turns:]

        try:
            response = await self.llm.complete(
                build_rewrite_messages(query, recent),
                # Temperature 0: this is a mechanical transformation, not
                # writing. Any sampling here is pure downside.
                temperature=0.0,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — degrade, never fail the request
            logger.warning("query rewrite failed, using the original query: %s", exc)
            return RewriteResult(
                original=query,
                rewritten=query,
                skipped_reason="failed",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

        candidate = clean_rewrite(response.text)
        acceptable, why = looks_like_a_rewrite(query, candidate)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not acceptable:
            logger.warning(
                "rejected rewrite (%s): %r -> %r", why, query, candidate[:200]
            )
            return RewriteResult(
                original=query, rewritten=query,
                skipped_reason=f"rejected:{why}", elapsed_ms=elapsed_ms,
            )

        return RewriteResult(
            original=query,
            rewritten=candidate,
            changed=candidate.strip().lower() != query.strip().lower(),
            elapsed_ms=elapsed_ms,
        )
