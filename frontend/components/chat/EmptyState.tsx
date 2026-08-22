"use client";

/**
 * What someone sees before they have asked anything.
 *
 * This is the first thing a stranger looks at, and the previous version was one
 * line of grey text and four unlabelled buttons. It now does three jobs:
 *
 *   1. Says what the assistant will and will not answer from, naming the
 *      current tenant — because "only this customer's documentation" is the
 *      claim, and stating it before the first question makes the abstention
 *      later read as design rather than failure.
 *   2. Restates the three promises as chips, each of which becomes an
 *      observable element once an answer arrives.
 *   3. Offers four questions in the order they are worth asking, each with a
 *      one-line "why" — the fastest way for someone new to see what the system
 *      does, and the reason the guided tour in the docs exists at all.
 */

import { ArrowRight, Check } from "@/components/ui/Icon";

export interface Example {
  q: string;
  why: string;
}

export const EXAMPLES: Example[] = [
  {
    q: "What is the webhook retry limit?",
    why: "the planted conflict — the docs say 3, the v2.4 changelog says 5",
  },
  {
    q: "What causes ERR_TIMEOUT_502?",
    why: "an exact identifier, where the keyword leg earns its place",
  },
  {
    q: "What is the capital of France?",
    why: "out of scope — abstains with zero LLM calls, and opens a ticket",
  },
  {
    q: "How do I rotate an API key?",
    why: "an ordinary question, answered and cited",
  },
];

const PROMISES = [
  "every claim cited",
  "every citation verified",
  "escalates instead of guessing",
];

export default function EmptyState({
  tenant,
  onAsk,
}: {
  tenant: string;
  onAsk: (question: string) => void;
}) {
  return (
    <div className="animate-fade-up pt-8">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Ask about Flowlytics</h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-slate-500">
        Answers come from{" "}
        <span className="font-medium text-ocean-700">{tenant}</span>&apos;s own documentation and
        nothing else. No other tenant&apos;s corpus is reachable, and nothing is answered from the
        model&apos;s own memory.
      </p>

      <ul className="mt-4 flex flex-wrap gap-2">
        {PROMISES.map((promise) => (
          <li
            key={promise}
            className="inline-flex items-center gap-1.5 rounded-md border border-line
                       bg-surface px-2 py-1 text-xs text-slate-600"
          >
            <Check size={12} className="text-emerald-600" />
            {promise}
          </li>
        ))}
      </ul>

      <p className="mt-8 text-2xs font-semibold uppercase tracking-[0.12em] text-slate-400">
        Try one of these
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {EXAMPLES.map((example) => (
          <button
            key={example.q}
            type="button"
            onClick={() => onAsk(example.q)}
            className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-left
                       transition-colors hover:border-ocean-300 hover:bg-ocean-50/50"
          >
            <span className="flex items-start gap-2">
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-slate-900">{example.q}</span>
                <span className="mt-1 block text-xs leading-relaxed text-slate-500">
                  {example.why}
                </span>
              </span>
              <ArrowRight
                size={14}
                className="mt-0.5 shrink-0 text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-ocean-500"
              />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
