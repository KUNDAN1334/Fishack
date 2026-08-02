"""Chat playground: the full pipeline, with every stage's decision visible.

    python scripts/chat_playground.py --tenant acme
    python scripts/chat_playground.py --query "what is the webhook retry limit?"
    python scripts/chat_playground.py --tenant acme --show-prompt

The retrieval playground answered "which chunks?". This one answers "and then
what happened?" — the rewrite, the gate's score against its threshold, the
answer streaming token by token, which sources it actually cited, and whether
each claim survived validation.

It keeps conversation history, so multi-turn rewriting is testable by hand:

    > what is the webhook retry limit?
    > what about the backoff schedule?      <- watch the rewrite line

Things worth trying, each of which exercises a different defense:
  * "what is the webhook retry limit?"   the planted conflict — the v2.4
                                         changelog and the older docs page are
                                         both retrieved; rule 4 should prefer
                                         the newer and say the older disagrees
  * "what is the capital of France?"     out of scope — must abstain with zero
                                         LLM calls
  * "ERR_TIMEOUT_502"                    exact identifier
  * "how do I rotate my API key?"        plausible but undocumented — the case
                                         where the gate passes and the MODEL
                                         has to decline
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.engine import create_pool  # noqa: E402
from app.embeddings.encoder import get_encoder  # noqa: E402
from app.embeddings.service import EmbeddingService  # noqa: E402
from app.generation.citations import CitationValidator  # noqa: E402
from app.generation.generator import Generator  # noqa: E402
from app.generation.models import ChatRequest, ChatResponse, Turn  # noqa: E402
from app.generation.pipeline import ChatPipeline  # noqa: E402
from app.generation.prompts import build_messages  # noqa: E402
from app.generation.rewriter import QueryRewriter  # noqa: E402
from app.llm.client import build_llm_client  # noqa: E402
from app.retrieval.service import build_retrieval_service  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

WIDTH = 92
RULE = "=" * WIDTH


def print_meta(data: dict) -> None:
    """Everything decided before the first token."""
    rewrite = data.get("rewrite") or {}
    if rewrite.get("changed"):
        print(f"rewrite   {rewrite['original']!r}\n       -> {rewrite['rewritten']!r}")
    elif rewrite.get("skipped_reason"):
        print(f"rewrite   skipped ({rewrite['skipped_reason']})")

    gate = data.get("gate") or {}
    if gate:
        verdict = "PASS" if gate["should_generate"] else "ABSTAIN"
        print(
            f"gate      {verdict}  {gate['score_kind']}_score={gate['top_score']:.4f} "
            f"vs threshold {gate['threshold']}  ({gate['reason']})"
        )

    citations = data.get("citations") or []
    if citations:
        print(f"sources   {len(citations)} offered to the model:")
        for citation in citations:
            contested = "  [CONTESTED]" if citation.get("is_contested") else ""
            where = citation.get("heading_path") or citation.get("title") or ""
            print(
                f"   [{citation['index']}] {citation['source_type']}/{where[:52]:<52}"
                f" {citation.get('doc_version') or '-':<6}"
                f" {citation.get('effective_date') or '-'}{contested}"
            )
    print("-" * WIDTH)


def print_report(response: ChatResponse) -> None:
    """The post-hoc verdict, plus the numbers that go on the trace row."""
    print("\n" + "-" * WIDTH)

    report = response.citation_report
    if report is not None:
        print(
            f"claims    {report.total_claims} checked, "
            f"grounding rate {report.grounding_rate:.0%}"
        )
        for check in report.claims:
            mark = "OK " if check.supported else "!! "
            similarity = f"{check.similarity:.2f}" if check.similarity is not None else " -- "
            problem = f"  <- {check.problem}" if check.problem else ""
            print(f"   {mark}[{similarity}] {check.claim[:60]}{problem}")
        if report.invalid_indices:
            print(f"   FABRICATED citations: {report.invalid_indices}")
        if report.unused_indices:
            print(f"   offered but unused: {report.unused_indices}")

    if response.escalation_id:
        print(f"escalated escalation_id={response.escalation_id}")

    failovers = (
        f"  failovers={[e['provider'] for e in response.failover_events]}"
        if response.failover_events else ""
    )
    print(
        f"timings   rewrite={response.rewrite_ms}ms  retrieval={response.retrieval_ms}ms  "
        f"rerank={response.rerank_ms}ms  generation={response.generation_ms}ms  "
        f"validation={response.validation_ms}ms  total={response.total_ms}ms"
    )
    print(
        f"cost      {response.provider}/{response.model}  "
        f"in={response.tokens_in} out={response.tokens_out}  "
        f"virtual=${response.virtual_cost_usd:.6f}{failovers}"
    )
    print(f"action    {response.action}   trace_id={response.trace_id}")
    print(RULE)


async def show_prompt(pipeline: ChatPipeline, tenant: str, query: str, settings) -> None:
    """Print the exact messages the model would receive.

    The single most useful debugging tool for a RAG system, and the one people
    build last. Almost every "why did it say that?" is answered by reading
    what it was actually shown.
    """
    from app.retrieval.tenant_scope import TenantScope
    from app.generation.models import build_citations

    retrieval = await pipeline.retrieval.retrieve(TenantScope(pipeline.pool, tenant), query)
    citations = build_citations(retrieval.results)
    messages = build_messages(
        query, citations, retrieval.results,
        abstention_message=settings.abstention_message,
    )
    print(f"\n{RULE}\nEXACT PROMPT ({len(messages)} messages)\n{RULE}")
    for message in messages:
        print(f"\n--- {message.role.upper()} " + "-" * (WIDTH - len(message.role) - 5))
        print(message.content)
    print(RULE)


async def run_turn(
    pipeline: ChatPipeline, tenant: str, query: str, history: list[Turn], conversation_id: str
) -> ChatResponse | None:
    request = ChatRequest(
        tenant_id=tenant, query=query, messages=history, conversation_id=conversation_id
    )
    print(f"\n{RULE}\nYOU: {query}\n{RULE}")

    final: ChatResponse | None = None
    printed_answer_header = False

    async for event in pipeline.stream(request):
        if event.type == "meta":
            print_meta(event.data or {})
        elif event.type == "delta":
            if not printed_answer_header:
                print("\nFISHLY: ", end="", flush=True)
                printed_answer_header = True
            # Printed as it arrives — this is what streaming is FOR, and it is
            # the only way to feel time-to-first-token rather than read it.
            print(event.text, end="", flush=True)
        elif event.type == "error":
            print(f"\n[ERROR] {event.text}")
        elif event.type == "final":
            final = ChatResponse.model_validate(event.data)

    print()
    if final:
        print_report(final)
    return final


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tenant", default="acme")
    parser.add_argument("--query", help="single turn, then exit")
    parser.add_argument("--show-prompt", action="store_true",
                        help="print the exact messages sent to the model, then exit")
    parser.add_argument("--no-rerank", action="store_true",
                        help="skip the cross-encoder (much faster startup and turns)")
    args = parser.parse_args()

    settings = get_settings()
    pool = await create_pool(settings.database_url)

    try:
        async with pool.acquire() as conn:
            chunk_count = await conn.fetchval(
                "SELECT count(*) FROM chunks WHERE tenant_id = $1 AND is_current", args.tenant
            )
        if not chunk_count:
            print(f"No chunks for tenant {args.tenant!r}. Run: python scripts/ingest.py run")
            return 1

        print(f"tenant {args.tenant}: {chunk_count} current chunks")
        print("loading models...")
        encoder = get_encoder(settings.embedding_model_name)
        embeddings = EmbeddingService(pool, encoder)
        llm = build_llm_client(settings)

        pipeline = ChatPipeline(
            pool=pool,
            retrieval=build_retrieval_service(
                embeddings, settings, with_reranker=not args.no_rerank
            ),
            rewriter=QueryRewriter(
                llm,
                enabled=settings.query_rewrite_enabled,
                history_turns=settings.query_rewrite_history_turns,
                max_tokens=settings.query_rewrite_max_tokens,
            ),
            generator=Generator(
                llm,
                abstention_message=settings.abstention_message,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            ),
            validator=CitationValidator(
                embeddings,
                similarity_threshold=settings.citation_similarity_threshold,
                enabled=settings.citation_validation_enabled,
                abstention_message=settings.abstention_message,
            ),
            embeddings=embeddings,
            settings=settings,
        )
        print(f"LLM chain: {' -> '.join(p.name for p in llm.providers)}")

        if args.show_prompt:
            await show_prompt(pipeline, args.tenant, args.query or "webhook retry limit", settings)
            return 0

        import uuid

        conversation_id = str(uuid.uuid4())
        history: list[Turn] = []

        if args.query:
            await run_turn(pipeline, args.tenant, args.query, history, conversation_id)
            return 0

        print(
            "\nMulti-turn chat. Empty line or Ctrl-C to quit, ':reset' to start over."
            "\nTry a follow-up like 'what about the backoff?' to see rewriting work."
        )
        while True:
            try:
                query = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not query:
                return 0
            if query == ":reset":
                history = []
                conversation_id = str(uuid.uuid4())
                print("(conversation cleared)")
                continue

            try:
                response = await run_turn(
                    pipeline, args.tenant, query, history, conversation_id
                )
            except Exception as exc:  # noqa: BLE001 — a REPL survives one bad turn
                print(f"ERROR: {type(exc).__name__}: {exc}")
                continue

            if response:
                # History carries the ANSWER TEXT only, never its sources —
                # the same rule the prompt builder follows. Re-injecting old
                # context would let turn 3 be answered from turn 1's chunks.
                history.append(Turn(role="user", content=query))
                history.append(Turn(role="assistant", content=response.answer))
    finally:
        try:
            await asyncio.shield(pool.close())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
