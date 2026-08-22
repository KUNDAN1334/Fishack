"use client";

/**
 * The assistant — `/try`.
 *
 * Moved here from `/` in the redesign. The front door is now the documentation,
 * because the first thirty seconds a stranger spends should explain what the
 * system is and what it proves; the running product sits one click away behind
 * a single primary action.
 *
 * Layout is two columns: conversation on the left, sources always visible on
 * the right (ADR-028). The right panel populates from the `meta` SSE event,
 * which the backend sends BEFORE the first token — so someone watches the
 * answer being built out of documents they can already see. Rendering
 * everything at once on `final` would be simpler and would delete the most
 * interesting thing this UI does.
 *
 * State lives here rather than in a store. One page, one conversation, no
 * cross-route sharing — `useState` is the honest amount of machinery, and a
 * reducer or a context provider would be structure without a reason.
 */

import { useCallback, useRef, useState } from "react";

import AnswerText from "@/components/chat/AnswerText";
import CitationsPanel from "@/components/chat/CitationsPanel";
import Composer from "@/components/chat/Composer";
import EmptyState from "@/components/chat/EmptyState";
import {
  CacheBadge,
  ConfidencePill,
  EscalationBanner,
  RewriteNote,
  TimingStrip,
} from "@/components/chat/Indicators";
import { FileText, ThumbsDown, ThumbsUp } from "@/components/ui/Icon";
import { sendFeedback, streamChat, toHistory } from "@/lib/chat";
import type { ChatMeta, ChatResponse, Turn } from "@/lib/types";

/**
 * The waiting state, before the first token.
 *
 * Three bars rather than the word "Searching…", and the label changes the
 * moment `meta` arrives — "Reading 5 sources" is a different, truer statement
 * than "Searching", and the transition between them is visible proof that the
 * sources landed before the text did.
 */
function AnswerSkeleton({ label }: { label: string }) {
  return (
    <div aria-live="polite">
      <p className="text-sm text-slate-400">{label}</p>
      <div className="mt-2.5 space-y-2">
        {["92%", "100%", "64%"].map((width, index) => (
          <div
            key={width}
            className="h-2.5 animate-pulse rounded-full bg-slate-200"
            style={{ width, animationDelay: `${index * 120}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [tenant, setTenant] = useState("acme");
  const [busy, setBusy] = useState(false);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // The panel always shows the LATEST assistant turn's sources. Showing an
  // older turn's would silently mismatch the answer being read.
  const latest = [...turns].reverse().find((turn) => turn.role === "assistant");
  const citations = latest?.response?.citations ?? latest?.meta?.citations ?? [];
  const validIndices = new Set(citations.map((citation) => citation.index));

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const patchLast = useCallback((patch: Partial<Turn>) => {
    setTurns((previous) => {
      const next = [...previous];
      const index = next.length - 1;
      if (index >= 0) next[index] = { ...next[index], ...patch };
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
      setTurns((previous) => [
        ...previous,
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
            setTurns((previous) => {
              const next = [...previous];
              const index = next.length - 1;
              next[index] = { ...next[index], content: next[index].content + text };
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
      setTurns((previous) => {
        const next = [...previous];
        next[index] = { ...next[index], rating };
        return next;
      });
      await sendFeedback(turn.response.trace_id, rating);
    },
    [turns],
  );

  function resetConversation() {
    setTurns([]);
    setConversationId(null);
    setActiveCitation(null);
  }

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        {/* Mobile-only header. Its single job is the sources trigger, which is
            how ADR-028's "below lg the evidence disappears" gap is closed. */}
        {citations.length > 0 && (
          <div className="flex shrink-0 items-center justify-between border-b border-line bg-surface px-4 py-2 lg:hidden">
            <span className="text-xs text-slate-500">
              answering as <span className="font-medium text-slate-800">{tenant}</span>
            </span>
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1
                         text-xs font-medium text-slate-700 hover:border-ocean-300 hover:text-ocean-700"
            >
              <FileText size={12} />
              <span className="figure">{citations.length}</span> sources
            </button>
          </div>
        )}

        <div ref={scrollRef} className="thin-scroll flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {turns.length === 0 && <EmptyState tenant={tenant} onAsk={ask} />}

            {turns.map((turn, index) =>
              turn.role === "user" ? (
                <div key={index} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ocean-600 px-4 py-2.5 text-sm text-white">
                    {turn.content}
                  </div>
                </div>
              ) : (
                <div key={index} className="max-w-[94%]">
                  <RewriteNote rewrite={turn.response?.rewrite ?? turn.meta?.rewrite} />

                  <div className="rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3.5">
                    {turn.error ? (
                      <p className="text-sm text-rose-700">{turn.error}</p>
                    ) : turn.pending && !turn.content ? (
                      <AnswerSkeleton
                        label={
                          turn.meta?.citations?.length
                            ? `Reading ${turn.meta.citations.length} sources…`
                            : "Searching the corpus…"
                        }
                      />
                    ) : (
                      // `aria-live="polite"` so a screen-reader user hears the
                      // answer as it arrives rather than only on completion.
                      <div aria-live="polite" className="text-sm text-slate-800">
                        <AnswerText
                          text={turn.content}
                          validIndices={validIndices}
                          activeIndex={activeCitation}
                          onCitationClick={(citationIndex) => {
                            setActiveCitation(citationIndex);
                            // On a phone the panel is a sheet, so a marker
                            // click has to open it or it does nothing at all.
                            if (window.matchMedia("(max-width: 1023px)").matches) {
                              setSheetOpen(true);
                            }
                          }}
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

                          <div className="ml-auto flex items-center gap-0.5">
                            {([1, -1] as const).map((value) => {
                              const Icon = value === 1 ? ThumbsUp : ThumbsDown;
                              const on = turn.rating === value;
                              return (
                                <button
                                  key={value}
                                  type="button"
                                  onClick={() => rate(index, value)}
                                  disabled={!turn.response?.trace_id}
                                  aria-label={value === 1 ? "Helpful" : "Not helpful"}
                                  aria-pressed={on}
                                  className={`rounded-md p-1.5 transition-colors disabled:opacity-30 ${
                                    on
                                      ? value === 1
                                        ? "bg-emerald-50 text-emerald-700"
                                        : "bg-rose-50 text-rose-700"
                                      : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                                  }`}
                                >
                                  <Icon size={14} />
                                </button>
                              );
                            })}
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
            resetConversation();
          }}
          onReset={resetConversation}
          hasHistory={turns.length > 0}
        />
      </section>

      <CitationsPanel
        citations={citations}
        report={latest?.response?.citation_report}
        activeIndex={activeCitation}
        onSelect={setActiveCitation}
        streaming={busy}
        sheetOpen={sheetOpen}
        onCloseSheet={() => setSheetOpen(false)}
      />
    </div>
  );
}
