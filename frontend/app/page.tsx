"use client";

/**
 * The chat page.
 *
 * Layout is two columns: conversation on the left, sources always visible on
 * the right (ADR-028). The right panel populates from the `meta` SSE event,
 * which the backend sends BEFORE the first token — so the user sees which
 * documents the answer is being built from while it is still being written.
 *
 * State lives here rather than in a store. One page, one conversation, no
 * cross-route sharing — `useState` is the honest amount of machinery, and a
 * reducer or a context provider would be structure without a reason.
 */

import { useCallback, useRef, useState } from "react";
import AnswerText from "@/components/AnswerText";
import CitationsPanel from "@/components/CitationsPanel";
import Composer from "@/components/Composer";
import {
  CacheBadge,
  ConfidencePill,
  EscalationBanner,
  RewriteNote,
  TimingStrip,
} from "@/components/Indicators";
import { sendFeedback, streamChat, toHistory } from "@/lib/chat";
import type { ChatMeta, ChatResponse, Turn } from "@/lib/types";

// Each of these exercises a different defence, and they are the fastest way
// for someone new to see what the system does.
const EXAMPLES = [
  { q: "What is the webhook retry limit?", why: "planted conflict — docs say 3, changelog says 5" },
  { q: "What causes ERR_TIMEOUT_502?", why: "exact identifier — where keyword search earns its place" },
  { q: "What is the capital of France?", why: "out of scope — must abstain without calling the model" },
  { q: "How do I rotate an API key?", why: "ordinary question, cited answer" },
];

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [tenant, setTenant] = useState("acme");
  const [busy, setBusy] = useState(false);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // The panel always shows the LATEST assistant turn's sources. Showing an
  // older turn's would silently mismatch the answer being read.
  const latest = [...turns].reverse().find((t) => t.role === "assistant");
  const citations = latest?.response?.citations ?? latest?.meta?.citations ?? [];
  const validIndices = new Set(citations.map((c) => c.index));

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const patchLast = useCallback((patch: Partial<Turn>) => {
    setTurns((prev) => {
      const next = [...prev];
      const i = next.length - 1;
      if (i >= 0) next[i] = { ...next[i], ...patch };
      return next;
    });
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const query = question.trim();
      if (!query || busy) return;

      const history = toHistory(turns);
      setInput("");
      setActiveCitation(null);
      setBusy(true);
      setTurns((prev) => [
        ...prev,
        { role: "user", content: query },
        { role: "assistant", content: "", pending: true },
      ]);
      scrollToBottom();

      const controller = new AbortController();
      abortRef.current = controller;

      await streamChat(
        { tenant_id: tenant, query, messages: history, conversation_id: conversationId },
        {
          onMeta: (meta: ChatMeta) => {
            // Sources land before any text — that ordering is the reason the
            // panel can populate while the answer types.
            patchLast({ meta });
            scrollToBottom();
          },
          onDelta: (text) => {
            setTurns((prev) => {
              const next = [...prev];
              const i = next.length - 1;
              next[i] = { ...next[i], content: next[i].content + text };
              return next;
            });
            scrollToBottom();
          },
          onFinal: (response: ChatResponse) => {
            patchLast({ response, pending: false, content: response.answer });
            // The server generates the conversation id; we echo it back so
            // multi-turn traces group together. The server stays stateless
            // (ADR-003).
            if (response.conversation_id) setConversationId(response.conversation_id);
            scrollToBottom();
          },
          onError: (message) => {
            if (message === "cancelled") patchLast({ pending: false, content: "(stopped)" });
            else patchLast({ pending: false, error: message });
          },
        },
        controller.signal,
      );

      setBusy(false);
      abortRef.current = null;
    },
    [busy, conversationId, patchLast, scrollToBottom, tenant, turns],
  );

  const rate = useCallback(
    async (index: number, rating: 1 | -1) => {
      const turn = turns[index];
      if (!turn.response?.trace_id) return;
      // Optimistic: the button lights immediately. A failed POST is not worth
      // interrupting someone's reading over — the flywheel loses one data
      // point, and nothing else breaks.
      setTurns((prev) => {
        const next = [...prev];
        next[index] = { ...next[index], rating };
        return next;
      });
      await sendFeedback(turn.response.trace_id, rating);
    },
    [turns],
  );

  return (
    <div className="flex h-full">
      <section className="flex flex-1 min-w-0 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto thin-scroll px-4 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {turns.length === 0 && (
              <div className="pt-10 text-center">
                <p className="text-2xl">🎣</p>
                <h1 className="mt-3 text-lg font-semibold text-slate-800">
                  Ask about Flowlytics
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  Answering as <span className="font-medium text-ocean-700">{tenant}</span>,
                  from that tenant&apos;s documentation only.
                </p>
                <div className="mt-6 grid gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example.q}
                      onClick={() => ask(example.q)}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left
                                 hover:border-ocean-300 hover:bg-ocean-50"
                    >
                      <p className="text-[13px] font-medium text-slate-800">{example.q}</p>
                      <p className="mt-0.5 text-[11px] text-slate-400">{example.why}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((turn, i) =>
              turn.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-ocean-600 px-4 py-2.5
                                  text-sm text-white">
                    {turn.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="max-w-[92%]">
                  <RewriteNote rewrite={turn.response?.rewrite ?? turn.meta?.rewrite} />

                  <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3">
                    {turn.error ? (
                      <p className="text-sm text-rose-600">{turn.error}</p>
                    ) : turn.pending && !turn.content ? (
                      <p className="text-sm text-slate-400">
                        {turn.meta?.citations?.length
                          ? `Reading ${turn.meta.citations.length} sources…`
                          : "Searching…"}
                      </p>
                    ) : (
                      <div className="text-sm text-slate-800">
                        <AnswerText
                          text={turn.content}
                          validIndices={validIndices}
                          activeIndex={activeCitation}
                          onCitationClick={setActiveCitation}
                          streaming={!!turn.pending}
                        />
                      </div>
                    )}

                    {turn.response?.action === "escalated" && (
                      <EscalationBanner response={turn.response} />
                    )}

                    {turn.response && (
                      <>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <ConfidencePill gate={turn.response.gate} />
                          <CacheBadge response={turn.response} />

                          <div className="ml-auto flex items-center gap-1">
                            {([1, -1] as const).map((value) => (
                              <button
                                key={value}
                                onClick={() => rate(i, value)}
                                disabled={!turn.response?.trace_id}
                                title={value === 1 ? "Helpful" : "Not helpful"}
                                className={`rounded-md px-2 py-1 text-sm transition-colors
                                  ${turn.rating === value
                                    ? value === 1
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-rose-100 text-rose-700"
                                    : "text-slate-400 hover:bg-slate-100 hover:text-slate-600"}`}
                              >
                                {value === 1 ? "👍" : "👎"}
                              </button>
                            ))}
                          </div>
                        </div>
                        <TimingStrip response={turn.response} />
                      </>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          onStop={() => abortRef.current?.abort()}
          busy={busy}
          tenant={tenant}
          onTenantChange={(next) => {
            // Switching tenant starts a new conversation. Carrying history
            // across would feed one tenant's answers into another's prompt as
            // context — not a chunk leak, but a leak.
            setTenant(next);
            setTurns([]);
            setConversationId(null);
            setActiveCitation(null);
          }}
          onReset={() => {
            setTurns([]);
            setConversationId(null);
            setActiveCitation(null);
          }}
          hasHistory={turns.length > 0}
        />
      </section>

      <CitationsPanel
        citations={citations}
        report={latest?.response?.citation_report}
        activeIndex={activeCitation}
        onSelect={setActiveCitation}
        streaming={busy}
      />
    </div>
  );
}
