"use client";

/**
 * The small status elements: confidence pill, escalation banner, cache badge,
 * rewrite note, and the per-stage timing strip.
 *
 * Grouped in one file because each is a handful of lines and they share one
 * job — making the pipeline's internal decisions visible to someone who is
 * deciding whether to trust the answer. Splitting them into five files would
 * scatter that intent.
 *
 * Two things changed in the redesign and both are about legibility rather than
 * looks. Every number here is now `figure` (mono, tabular), so scores,
 * latencies and costs read as data rather than as prose at the same weight as
 * the sentence around them. And the `title=` attributes that carried the real
 * explanations — the confidence scale, the cache semantics, the cost
 * methodology — are now visible text or `<details>`, because a tooltip is
 * invisible on touch and unreachable by keyboard, and this content is not
 * decoration.
 */

import type { ChatResponse, GateDecision, RewriteResult } from "@/lib/types";
import { AlertTriangle, Bolt, Search, ShieldCheck } from "@/components/ui/Icon";

/* ------------------------------------------------------------ confidence -- */

/**
 * The confidence pill.
 *
 * Shows the raw number AND the scale it is on. That second part is not
 * decoration: the backend produces two kinds of score roughly 30x apart — the
 * reranker's sigmoid (0-1) and the RRF fusion score (~0.016-0.033) — so "0.02"
 * is meaningless alone. It is a healthy fusion score and a catastrophic
 * reranker score. The same reasoning put `score_kind` on the trace row in the
 * backend (ADR-015).
 *
 * The word (`strong` / `adequate` / `below threshold`) comes first because
 * colour is never the only signal here, and because the word is what a reader
 * skimming a long conversation actually needs.
 */
export function ConfidencePill({ gate }: { gate: GateDecision | null | undefined }) {
  if (!gate || gate.score_kind === "none") return null;

  const { top_score: score, threshold, score_kind: kind } = gate;
  // Ratio against the threshold, not the absolute value — that is the only
  // comparison meaning the same thing on both scales.
  const ratio = threshold > 0 ? score / threshold : 1;
  const tone =
    ratio >= 1.6
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : ratio >= 1.0
        ? "border-ocean-200 bg-ocean-50 text-ocean-800"
        : "border-amber-200 bg-amber-50 text-amber-800";
  const label = ratio >= 1.6 ? "strong" : ratio >= 1.0 ? "adequate" : "below threshold";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-2xs ${tone}`}
    >
      <ShieldCheck size={12} />
      <span className="font-semibold">{label}</span>
      <span className="figure opacity-80">
        {score.toFixed(3)} / {threshold}
      </span>
      <span className="rounded-sm bg-white/60 px-1 font-mono text-[9.5px] uppercase tracking-wide">
        {kind}
      </span>
    </span>
  );
}

/* ------------------------------------------------------------ escalation -- */

/**
 * Shown whenever Fishack declined to answer.
 *
 * Deliberately NOT styled as an error. Abstaining is the system working —
 * Design.md's thesis is that in B2B support a wrong answer costs more than no
 * answer — and red would train people to read correct behaviour as a fault.
 * This is the single most important colour decision in the application.
 *
 * `role="status"` rather than `role="alert"`: the banner should be announced
 * once, after the answer region settles, not interrupt it.
 */
export function EscalationBanner({ response }: { response: ChatResponse }) {
  const reason =
    response.gate?.reason === "no_results"
      ? "Nothing in your documentation matched this question."
      : response.gate?.reason === "below_threshold"
        ? "The closest sources weren't a strong enough match to answer from."
        : "The assistant reviewed the sources and couldn't answer from them.";

  return (
    <div
      role="status"
      className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-600" />
        <div className="text-sm text-amber-900">
          <p className="font-semibold">Escalated to a human agent — this is the system working</p>
          <p className="mt-1 text-amber-800">{reason}</p>
          {response.escalation_id && (
            <p className="mt-2 text-xs leading-relaxed text-amber-800/90">
              Ticket{" "}
              <code className="rounded-sm bg-amber-100 px-1 py-px font-mono">
                {response.escalation_id.slice(0, 8)}
              </code>{" "}
              carries the conversation and the top ten sources that were searched, with their
              scores — so the agent does not repeat the search that just failed.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- cache -- */

/**
 * Cache badge.
 *
 * A semantic hit means the reader is looking at an answer written for a
 * DIFFERENT question, which they deserve to know while judging whether it fits.
 * So the two hit kinds are labelled differently rather than sharing one
 * "cached" chip, and the similarity is shown for the semantic one.
 */
export function CacheBadge({ response }: { response: ChatResponse }) {
  if (!response.cache_status || response.cache_status === "miss") return null;
  const semantic = response.cache_status === "semantic_hit";

  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface-sunken px-2 py-1 text-2xs text-slate-600">
      <Bolt size={12} className="text-slate-400" />
      <span className="font-semibold">{semantic ? "similar question" : "cached"}</span>
      {semantic && response.cache_similarity != null && (
        <span className="figure opacity-80">{response.cache_similarity.toFixed(3)}</span>
      )}
    </span>
  );
}

/* --------------------------------------------------------------- rewrite -- */

/** Shown only when rewriting changed the query — otherwise it is noise. */
export function RewriteNote({ rewrite }: { rewrite: RewriteResult | null | undefined }) {
  if (!rewrite?.changed) return null;
  return (
    <p className="mb-2 flex items-center gap-1.5 text-xs text-slate-400">
      <Search size={12} />
      searched for <span className="text-slate-600">{rewrite.rewritten}</span>
    </p>
  );
}

/* --------------------------------------------------------------- timings -- */

/**
 * Per-stage latency, cost, model, and any degraded leg.
 *
 * A single total tells you it was slow; the breakdown tells you which stage
 * owns it, and on this system the answer is almost always the cross-encoder.
 * Stages reading zero are dropped rather than shown as `0ms`, since zero here
 * means "did not run" — a first-turn query skips rewriting entirely — and
 * printing it as a measurement would be a small lie repeated on every answer.
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
    <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-2.5 text-2xs text-slate-400">
      {shown.map(([name, ms]) => (
        <span key={name}>
          {name} <span className="figure text-slate-600">{ms}ms</span>
        </span>
      ))}
      <span className="text-slate-500">
        total <span className="figure font-medium text-slate-800">{response.total_ms}ms</span>
      </span>

      {response.virtual_cost_usd > 0 && (
        <span>
          <span className="figure text-slate-600">${response.virtual_cost_usd.toFixed(6)}</span>{" "}
          {/* The word matters more than the number. Detached from it, this
              figure reads as a bill; the actual spend on free tiers is $0. */}
          <span className="text-slate-400">virtual</span>
        </span>
      )}

      {response.model && <span className="figure text-slate-400">{response.model}</span>}

      {response.degraded_legs.length > 0 && (
        <span className="inline-flex items-center gap-1 rounded-sm bg-amber-50 px-1.5 py-px text-amber-700">
          <AlertTriangle size={11} />
          degraded: {response.degraded_legs.join(", ")} — built on less evidence than usual
        </span>
      )}
    </div>
  );
}
