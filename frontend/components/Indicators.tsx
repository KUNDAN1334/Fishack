"use client";

/**
 * The small status elements: confidence pill, escalation banner, cache badge,
 * rewrite note, and the per-stage timing strip.
 *
 * Grouped in one file because each is a handful of lines and they share one
 * job — making the pipeline's internal decisions visible to a user who is
 * deciding whether to trust the answer. Splitting them into five files would
 * scatter that intent.
 */

import type { ChatResponse, GateDecision, RewriteResult } from "@/lib/types";

/* ------------------------------------------------------------ confidence -- */

/**
 * The confidence pill.
 *
 * Shows the raw number AND the scale it is on. That second part is not
 * decoration: the backend produces two kinds of score ~30x apart — the
 * reranker's sigmoid (0-1) and the RRF fusion score (~0.016-0.033) — so
 * "0.02" is meaningless on its own. It is a healthy fusion score and a
 * catastrophic reranker score. The same reasoning drove `score_kind` onto the
 * trace row in the backend (ADR-015).
 */
export function ConfidencePill({ gate }: { gate: GateDecision | null | undefined }) {
  if (!gate || gate.score_kind === "none") return null;

  const { top_score: score, threshold, score_kind: kind } = gate;
  // Ratio against the threshold, not the absolute value — that is the only
  // comparison that means the same thing on both scales.
  const ratio = threshold > 0 ? score / threshold : 1;
  const tone =
    ratio >= 1.6 ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : ratio >= 1.0 ? "bg-ocean-50 text-ocean-700 ring-ocean-300"
    : "bg-amber-50 text-amber-700 ring-amber-200";
  const label = ratio >= 1.6 ? "strong" : ratio >= 1.0 ? "adequate" : "below threshold";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ring-1 ${tone}`}
      title={`Top ${kind} score ${score.toFixed(4)} against a ${threshold} threshold. The reranker and fusion scales differ by ~30x, so the scale is shown too.`}
    >
      <span className="font-medium">{label}</span>
      <span className="opacity-70 tabular-nums">
        {score.toFixed(3)} / {threshold} ({kind})
      </span>
    </span>
  );
}

/* ------------------------------------------------------------ escalation -- */

/**
 * Shown whenever Fishly declined to answer.
 *
 * Deliberately NOT styled as an error. Abstaining is the system working —
 * Design.md's whole thesis is that in B2B support a wrong answer costs more
 * than no answer. Red would train users to read correct behaviour as a fault.
 */
export function EscalationBanner({ response }: { response: ChatResponse }) {
  const reason =
    response.gate?.reason === "no_results"
      ? "Nothing in your documentation matched this question."
      : response.gate?.reason === "below_threshold"
        ? "The closest sources weren't a strong enough match to answer from."
        : "The assistant reviewed the sources and couldn't answer from them.";

  return (
    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
      <div className="flex items-start gap-2">
        <span className="text-amber-600 text-sm mt-px">⚑</span>
        <div className="text-[13px] text-amber-900">
          <p className="font-medium">Escalated to a human agent</p>
          <p className="mt-0.5 text-amber-800/90">{reason}</p>
          {response.escalation_id && (
            <p className="mt-1.5 text-[11px] text-amber-700/80">
              Ticket{" "}
              <code className="rounded bg-amber-100 px-1">
                {response.escalation_id.slice(0, 8)}
              </code>{" "}
              created with the full conversation and the sources that were searched — so
              the agent doesn&apos;t repeat the search that just failed.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- cache -- */

/**
 * Cache badge. Shown because a semantic hit means the user is reading an
 * answer written for a DIFFERENT question — which is worth being able to see
 * when judging whether it fits.
 */
export function CacheBadge({ response }: { response: ChatResponse }) {
  if (!response.cache_status || response.cache_status === "miss") return null;
  const semantic = response.cache_status === "semantic_hit";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5
                 text-[11px] text-slate-600 ring-1 ring-slate-200"
      title={
        semantic
          ? `Served from cache after matching a similar earlier question (similarity ${response.cache_similarity?.toFixed(3)}).`
          : "Served from cache — this exact question was answered before."
      }
    >
      ⚡ {semantic ? "similar question" : "cached"}
    </span>
  );
}

/* --------------------------------------------------------------- rewrite -- */

/** Shown only when rewriting changed the query — otherwise it is noise. */
export function RewriteNote({ rewrite }: { rewrite: RewriteResult | null | undefined }) {
  if (!rewrite?.changed) return null;
  return (
    <p className="mb-1.5 text-[11px] text-slate-400">
      searched for: <span className="italic text-slate-500">{rewrite.rewritten}</span>
    </p>
  );
}

/* --------------------------------------------------------------- timings -- */

/**
 * Per-stage latency. A single total tells you it was slow; the breakdown tells
 * you which stage owns it — and on this system the answer is almost always the
 * cross-encoder.
 */
export function TimingStrip({ response }: { response: ChatResponse }) {
  const stages: [string, number][] = [
    ["rewrite", response.rewrite_ms],
    ["retrieval", response.retrieval_ms],
    ["rerank", response.rerank_ms],
    ["generation", response.generation_ms],
    ["validation", response.validation_ms],
  ];
  const shown = stages.filter(([, ms]) => ms > 0);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
      {shown.map(([name, ms]) => (
        <span key={name} className="tabular-nums">
          {name} <span className="text-slate-500">{ms}ms</span>
        </span>
      ))}
      <span className="tabular-nums text-slate-500">total {response.total_ms}ms</span>
      {response.virtual_cost_usd > 0 && (
        <span
          className="tabular-nums"
          title="What this WOULD cost at paid-API prices. We run on free tiers, so actual spend is $0."
        >
          ~${response.virtual_cost_usd.toFixed(6)}
        </span>
      )}
      {response.model && <span className="text-slate-400">{response.model}</span>}
      {response.degraded_legs.length > 0 && (
        <span
          className="text-amber-600"
          title="One retrieval leg failed, so this answer was built on less evidence than usual."
        >
          degraded: {response.degraded_legs.join(", ")}
        </span>
      )}
    </div>
  );
}
