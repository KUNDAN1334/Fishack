"""Prompt construction — a direct implementation of Design.md §7.

Every prompt in Fishack lives in this one file, as module-level constants with
the reasoning beside them. That is deliberate: prompts are the part of a RAG
system most likely to be edited under pressure ("just add one more rule"), and
the fastest way to lose track of why a system behaves the way it does is to
have prompt fragments scattered across the modules that use them.

Design.md §7 prescribes five rules, and each one defends a different failure:

  1. every claim carries a [n] marker      -> makes ungrounded text visible
  2. abstain verbatim when context is thin -> gives the model an exit that
                                              isn't guessing
  3. no outside knowledge, ever            -> the closed-book constraint
  4. on conflict prefer newest, flag it    -> the stale-data defense (§11a)
  5. concise, technical, actionable        -> it is a support answer

Rule 1 is the load-bearing one. An answer sentence without a citation is the
strongest available signal that the model strayed outside its context, which
is precisely what citations.py checks for afterwards. The prompt does not
*enforce* grounding — nothing in a prompt enforces anything — it makes
violations detectable.
"""

from __future__ import annotations

import datetime as dt

from app.generation.models import Citation, Turn
from app.llm.base import ChatMessage
from app.retrieval.models import ScoredChunk

# --------------------------------------------------------------- system ----

# Note the shape: rules BEFORE context, context before question. Models attend
# most reliably to the start and end of a prompt, so the instructions go first
# and the actual question goes last, with the bulk of the retrieved text
# between them. Putting the question first and the rules last is a common and
# expensive mistake — the rules end up competing with 2000 tokens of context
# for the model's attention.
SYSTEM_PROMPT = """You are a customer support assistant for Flowlytics, a B2B analytics and billing platform.

Answer ONLY using the numbered context sources provided below.

RULES:
1. Every factual claim in your answer MUST be followed by a citation marker
   like [1] or [2], referring to the numbered source it came from. A sentence
   with no citation marker is not allowed.
2. If the context does not contain enough information to answer confidently,
   respond EXACTLY with:
   "{abstention}"
   Do not apologise, explain, or add anything else to that sentence.
3. Do NOT use any knowledge outside the provided context, even if you are
   confident you know the answer. If the context is silent, you abstain.
4. If two sources conflict, follow the MORE RECENT one (compare the dates
   given with each source) and explicitly tell the user that the older source
   says something different, citing both.
5. Keep answers concise, technical, and actionable. Two to five sentences is
   usually right. Do not restate the question.
"""

# --------------------------------------------------------------- few-shot --

# Design.md §7: "explicit instruction + few-shot examples of when to abstain
# (helps a LOT more than instruction alone)".
#
# Why this is true, and worth being able to explain: an instruction tells the
# model what the rule is; a demonstration tells it what COMPLIANCE LOOKS LIKE.
# Models are strongly biased toward being helpful, and "I don't know" reads as
# unhelpful — so without a worked example of a refusal, a model with
# tangentially-related context will reliably produce a plausible answer from
# it rather than abstain.
#
# The examples are given as real conversation turns rather than as text inside
# the system prompt, because that is the format the model was instruction-tuned
# on. An example embedded in a system prompt is something to read; an example
# in the message history is something to imitate.
FEW_SHOT_EXAMPLES: list[tuple[str, str]] = [
    # 1. Out of scope: context is topically nearby but answers a different
    #    question. This is the hard case — the easy case (empty context) never
    #    reaches the model, because the confidence gate abstains first.
    (
        """SOURCES:
[1] (docs: Billing Plans, v2.3, effective 2026-02-10)
Flowlytics offers Starter, Growth and Enterprise plans. Growth includes 5
million events per month and unlimited dashboards.

QUESTION:
How do I rotate my API key?""",
        "{abstention}",
    ),
    # 2. Conflict: the changelog supersedes a fact on a still-correct docs
    #    page. Demonstrates rule 4's full shape — answer with the newer value,
    #    cite both, name the discrepancy. Instruction alone reliably produces
    #    only half of this (the model picks the newer fact and says nothing
    #    about the older one).
    (
        """SOURCES:
[1] (docs: Webhooks Overview > Retry Logic, v2.2, effective 2026-03-12)
Webhook deliveries are retried up to 3 times using exponential backoff.

[2] (changelog: v2.4, effective 2026-06-10)
Webhook retry limit increased to 5 attempts. Backoff schedule unchanged.

QUESTION:
How many times will a failed webhook be retried?""",
        "Failed webhooks are retried up to 5 times with exponential backoff [2]. "
        "Note that the Webhooks Overview documentation still states a limit of 3 "
        "attempts [1]; that page predates the v2.4 change on 2026-06-10 and is out "
        "of date.",
    ),
    # 3. Normal answer: short, cited per claim, no padding. Included because
    #    without a positive example the abstention examples bias the model
    #    toward over-abstaining — the failure mode you create while fixing the
    #    other one.
    (
        """SOURCES:
[1] (docs: API Rate Limits > Handling 429 Responses, v2.3, effective 2026-04-02)
When the API rate limit is exceeded, requests return HTTP 429 with a
Retry-After header indicating how many seconds to wait before retrying.

QUESTION:
What happens when I hit the rate limit?""",
        "Requests over the limit return HTTP 429 [1]. The response carries a "
        "Retry-After header telling you how many seconds to wait before retrying "
        "[1].",
    ),
]


def format_source(citation: Citation, chunk: ScoredChunk) -> str:
    """Render one numbered source block.

    The header line carries provenance the model needs for rule 4 — source
    type, title, version, date. Dates are spelled out rather than left implicit
    because "prefer the more recent one" is impossible to follow if the model
    cannot see which is more recent, and that is the single most common way
    the conflict rule fails in practice.
    """
    parts = [citation.source_type]
    if citation.title:
        parts.append(citation.title)
    if citation.heading_path and citation.heading_path != citation.title:
        parts.append(citation.heading_path)

    meta = []
    if citation.doc_version:
        meta.append(citation.doc_version)
    if citation.effective_date:
        meta.append(f"effective {citation.effective_date.isoformat()}")

    header = f"[{citation.index}] ({': '.join(parts[:2])}"
    if len(parts) > 2:
        header += f" > {parts[2]}"
    if meta:
        header += f", {', '.join(meta)}"
    header += ")"

    # A chunk flagged at ingestion as contradicted by a newer changelog entry
    # (ADR-009). We say so IN the prompt rather than trusting the model to
    # notice two dates: ingestion already did this analysis and it would be
    # wasteful — and less reliable — to make the model redo it.
    if citation.is_contested:
        header += "\n    NOTE: a newer changelog entry contradicts part of this source."

    return f"{header}\n{chunk.chunk.body}"


def build_context_block(citations: list[Citation], results: list[ScoredChunk]) -> str:
    """Assemble the numbered SOURCES section.

    `citations` and `results` are positionally aligned by `build_citations`,
    and this is the only place that alignment is relied on — which is why the
    numbering is computed once, upstream, and passed in rather than recomputed
    here.
    """
    blocks = [format_source(citation, scored) for citation, scored in zip(citations, results)]
    return "SOURCES:\n\n" + "\n\n".join(blocks)


def build_messages(
    query: str,
    citations: list[Citation],
    results: list[ScoredChunk],
    *,
    abstention_message: str,
    history: list[Turn] | None = None,
    include_few_shot: bool = True,
    today: dt.date | None = None,
) -> list[ChatMessage]:
    """Build the full message list for a grounded answer.

    Ordering, and why:
      system            rules, with today's date so "more recent" is anchorable
      few-shot pairs    what compliance looks like (abstain / conflict / normal)
      history           prior turns, for tone and pronoun continuity
      user              SOURCES + QUESTION, together, last

    History is included but *truncated by the caller*, and it deliberately does
    NOT carry the earlier turns' sources. Re-injecting old context would let
    the model answer turn 3 from turn 1's chunks, which is a genuinely nasty
    grounding bug: the citation markers would refer to sources not in the
    current numbering, and validation would flag them as fabricated.
    """
    today = today or dt.date.today()
    system = SYSTEM_PROMPT.format(abstention=abstention_message)
    system += (
        f"\nToday's date is {today.isoformat()}. Use it when judging which "
        "source is more recent.\n"
    )

    messages = [ChatMessage(role="system", content=system)]

    if include_few_shot:
        for example_user, example_assistant in FEW_SHOT_EXAMPLES:
            messages.append(ChatMessage(role="user", content=example_user))
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=example_assistant.format(abstention=abstention_message),
                )
            )

    for turn in history or []:
        messages.append(ChatMessage(role=turn.role, content=turn.content))

    messages.append(
        ChatMessage(
            role="user",
            content=f"{build_context_block(citations, results)}\n\nQUESTION:\n{query}",
        )
    )
    return messages


# ------------------------------------------------------- query rewriting ----

# A separate, much smaller prompt. Two reasons it is not folded into the main
# one: it runs against a different (cheaper, faster) call with a tiny token
# budget, and mixing "rewrite this question" with "answer this question" in one
# prompt invites the model to do the second when asked for the first — which is
# exactly the failure rewriter.py guards against by rejecting long outputs.
REWRITE_SYSTEM_PROMPT = """You rewrite follow-up questions into standalone questions.

Given a conversation and the user's latest message, output a single question
that can be understood WITHOUT the conversation — resolve pronouns ("it",
"that", "those") and implicit references ("what about the retry logic?") using
the earlier turns.

RULES:
- Output ONLY the rewritten question. No preamble, no explanation, no quotes.
- Do NOT answer the question.
- Keep the user's own terminology, especially error codes, version numbers and
  product names. Never "correct" or expand an identifier like ERR_TIMEOUT_502.
- If the latest message is already standalone, output it unchanged.
"""


def build_rewrite_messages(query: str, history: list[Turn]) -> list[ChatMessage]:
    """Build the rewriting call.

    History is rendered into a single user message rather than replayed as
    real turns, because we want the model treating the conversation as *data
    to analyse*, not as a conversation it is participating in. Replaying it as
    turns reliably produces an answer to the question instead of a rewrite.
    """
    transcript = "\n".join(
        f"{'User' if turn.role == 'user' else 'Assistant'}: {turn.content}"
        for turn in history
    )
    return [
        ChatMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=(
                f"CONVERSATION SO FAR:\n{transcript}\n\n"
                f"LATEST USER MESSAGE:\n{query}\n\n"
                "STANDALONE QUESTION:"
            ),
        ),
    ]
