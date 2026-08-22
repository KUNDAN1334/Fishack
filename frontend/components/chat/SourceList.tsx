"use client";

/**
 * The list of sources offered to the model, and what happened to each.
 *
 * Extracted from the panel so the desktop rail and the mobile sheet render the
 * identical list. Two copies of this markup would drift, and the thing that
 * would drift first is the contested badge — which is the most important thing
 * on the screen.
 *
 * What each part is for:
 *
 *   `superseded in part`  A newer changelog entry contradicts this chunk.
 *                         Computed at INGESTION time (ADR-009), never guessed
 *                         in the browser. Amber, because a contested source is
 *                         not an error — it is the corpus being honest about
 *                         itself, and the answer may well have handled it.
 *   `not cited`           Retrieved, offered to the model, and unused. Dimmed
 *                         rather than hidden: "we searched this and the answer
 *                         did not need it" is information, and in aggregate it
 *                         is a retrieval-precision signal.
 *   per-claim verdicts    The literal "verified" from the tagline, made
 *                         inspectable. Emerald supports, rose weak match.
 */

import { useEffect, useRef } from "react";

import type { Citation, CitationReport } from "@/lib/types";
import { AlertTriangle, Check, Close, FileText, History, Ticket } from "@/components/ui/Icon";

const SOURCE_STYLE: Record<
  string,
  { label: string; className: string; icon: typeof FileText }
> = {
  docs: { label: "docs", className: "bg-ocean-50 text-ocean-700 border-ocean-200", icon: FileText },
  changelog: {
    label: "changelog",
    className: "bg-violet-50 text-violet-700 border-violet-200",
    icon: History,
  },
  ticket: {
    label: "ticket",
    className: "bg-emerald-50 text-emerald-700 border-emerald-200",
    icon: Ticket,
  },
};

export default function SourceList({
  citations,
  report,
  activeIndex,
  onSelect,
}: {
  citations: Citation[];
  report: CitationReport | null | undefined;
  activeIndex: number | null;
  onSelect: (index: number | null) => void;
}) {
  const refs = useRef<Record<number, HTMLLIElement | null>>({});

  // Scroll the selected source into view when a [n] marker is clicked.
  // `nearest` rather than `center` so an already-visible source does not jump.
  useEffect(() => {
    if (activeIndex == null) return;
    refs.current[activeIndex]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeIndex]);

  return (
    <ul className="space-y-2">
      {citations.map((citation) => {
        const active = citation.index === activeIndex;
        const style = SOURCE_STYLE[citation.source_type] ?? {
          label: citation.source_type,
          className: "bg-slate-100 text-slate-600 border-line",
          icon: FileText,
        };
        const SourceIcon = style.icon;
        const claims =
          report?.claims.filter((claim) => claim.cited_indices.includes(citation.index)) ?? [];

        return (
          <li
            key={citation.chunk_id}
            ref={(el) => {
              refs.current[citation.index] = el;
            }}
          >
            <div
              className={`rounded-lg border transition-colors ${
                active
                  ? "border-ocean-400 bg-ocean-50/60 ring-1 ring-ocean-200"
                  : citation.was_cited
                    ? "border-line bg-surface hover:border-ocean-300"
                    : "border-line/70 bg-surface-sunken/60"
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(active ? null : citation.index)}
                aria-expanded={active}
                className="flex w-full items-start gap-2.5 p-3 text-left"
              >
                <span
                  className={`mt-px shrink-0 rounded-sm px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                    active ? "bg-ocean-600 text-white" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {citation.index}
                </span>

                <span className="min-w-0 flex-1">
                  <span
                    className={`block text-sm font-medium leading-snug ${
                      citation.was_cited ? "text-slate-900" : "text-slate-500"
                    }`}
                  >
                    {citation.heading_path || citation.title}
                  </span>

                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span
                      className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-[10px] ${style.className}`}
                    >
                      <SourceIcon size={10} />
                      {style.label}
                    </span>
                    {citation.doc_version && (
                      <span className="figure text-[10px] text-slate-400">
                        {citation.doc_version}
                      </span>
                    )}
                    {citation.effective_date && (
                      <span className="figure text-[10px] text-slate-400">
                        {citation.effective_date}
                      </span>
                    )}
                    {citation.is_contested && (
                      <span className="inline-flex items-center gap-1 rounded-sm border border-amber-200 bg-amber-100 px-1.5 py-px text-[10px] font-medium text-amber-800">
                        <AlertTriangle size={10} />
                        superseded in part
                      </span>
                    )}
                    {!citation.was_cited && (
                      <span className="text-[10px] text-slate-400">not cited</span>
                    )}
                  </span>
                </span>
              </button>

              {active && (
                <div className="animate-fade-up border-t border-ocean-200/70 px-3 pb-3 pt-2.5">
                  <p className="figure mb-2 break-all text-[10px] uppercase tracking-wide text-slate-400">
                    {citation.source_path}
                  </p>

                  {claims.map((claim, i) => (
                    <div
                      key={i}
                      className={`mb-1.5 rounded-md px-2 py-1.5 text-xs leading-snug ${
                        claim.supported
                          ? "bg-emerald-50 text-emerald-900"
                          : "bg-rose-50 text-rose-900"
                      }`}
                    >
                      <span className="inline-flex items-center gap-1 font-medium">
                        {claim.supported ? <Check size={11} /> : <Close size={11} />}
                        {claim.supported ? "supports" : "weak match"}
                        {claim.similarity != null && (
                          <span className="figure opacity-70">
                            {claim.similarity.toFixed(2)}
                          </span>
                        )}
                      </span>
                      <p className="mt-0.5 opacity-80">
                        {claim.claim.slice(0, 160)}
                        {claim.claim.length > 160 ? "…" : ""}
                      </p>
                    </div>
                  ))}

                  <p className="text-xs text-slate-500">
                    retrieval score{" "}
                    <span className="figure text-slate-700">{citation.score.toFixed(3)}</span>
                  </p>
                </div>
              )}
            </div>
          </li>
        );
      })}

      {report && report.invalid_indices.length > 0 && (
        <li className="rounded-lg border border-rose-200 bg-rose-50 p-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-rose-800">
            <AlertTriangle size={13} />
            Fabricated citations: <span className="figure">{report.invalid_indices.join(", ")}</span>
          </p>
          <p className="mt-1 text-xs leading-relaxed text-rose-700">
            The answer referenced sources that were never provided to the model. Flagged rather
            than hidden — the answer may still be correct, and you should be able to see the
            discrepancy.
          </p>
        </li>
      )}
    </ul>
  );
}
