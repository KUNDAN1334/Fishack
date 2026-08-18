"use client";

/**
 * The sources panel (ADR-028, Design.md §13e).
 *
 * Always visible, never behind a click. Two reasons:
 *
 *   1. The backend sends its `meta` event — the citations — BEFORE the first
 *      token of the answer. So the sources can render while the answer is
 *      still typing, and the user watches it being built out of documents
 *      they can already see. That ordering was designed for this.
 *
 *   2. The product's entire claim is "every claim cited, verified and
 *      confidence-gated". Hiding the evidence behind a click contradicts the
 *      promise in the header.
 *
 * Clicking a [n] marker in the answer scrolls to and expands the matching
 * source — Design.md §13e's highlight-on-hover pattern, at the granularity we
 * actually have (chunk, not sentence).
 */

import { useEffect, useRef } from "react";
import type { Citation, CitationReport } from "@/lib/types";

interface Props {
  citations: Citation[];
  report: CitationReport | null | undefined;
  activeIndex: number | null;
  onSelect: (index: number | null) => void;
  streaming: boolean;
}

const SOURCE_STYLE: Record<string, { label: string; className: string }> = {
  docs: { label: "docs", className: "bg-ocean-50 text-ocean-700 ring-ocean-200" },
  changelog: { label: "changelog", className: "bg-violet-50 text-violet-700 ring-violet-200" },
  ticket: { label: "ticket", className: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
};

export default function CitationsPanel({
  citations,
  report,
  activeIndex,
  onSelect,
  streaming,
}: Props) {
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  // Scroll the selected source into view when a marker is clicked. `nearest`
  // rather than `center` so an already-visible source doesn't jump.
  useEffect(() => {
    if (activeIndex == null) return;
    refs.current[activeIndex]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeIndex]);

  if (citations.length === 0) {
    return (
      <aside className="hidden lg:flex w-[380px] shrink-0 border-l border-slate-200 bg-white
                        flex-col items-center justify-center px-8 text-center">
        <span className="text-3xl opacity-40">📄</span>
        <p className="mt-3 text-sm font-medium text-slate-500">Sources appear here</p>
        <p className="mt-1 text-xs text-slate-400 leading-relaxed">
          {streaming
            ? "Searching the knowledge base…"
            : "Every answer shows the exact document chunks it was built from — with version, date, and whether a newer entry contradicts them."}
        </p>
      </aside>
    );
  }

  const unsupported = report?.claims.filter((c) => !c.supported) ?? [];

  return (
    <aside className="hidden lg:flex w-[380px] shrink-0 border-l border-slate-200 bg-white flex-col">
      <div className="shrink-0 border-b border-slate-200 px-4 py-2.5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Sources</h2>
          <span className="text-[11px] text-slate-400">
            {citations.filter((c) => c.was_cited).length} of {citations.length} cited
          </span>
        </div>
        {report && report.claims.length > 0 && (
          <p className="mt-1 text-[11px] text-slate-500">
            {unsupported.length === 0 ? (
              <span className="text-emerald-600">
                ✓ all {report.claims.length} claims matched their cited source
              </span>
            ) : (
              <span className="text-rose-600">
                {unsupported.length} of {report.claims.length} claims couldn&apos;t be
                matched to their source
              </span>
            )}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto thin-scroll px-3 py-3 space-y-2">
        {citations.map((citation) => {
          const active = citation.index === activeIndex;
          const style = SOURCE_STYLE[citation.source_type] ?? {
            label: citation.source_type,
            className: "bg-slate-100 text-slate-600 ring-slate-200",
          };

          return (
            <div
              key={citation.chunk_id}
              ref={(el) => { refs.current[citation.index] = el; }}
              onClick={() => onSelect(active ? null : citation.index)}
              className={`cursor-pointer rounded-lg border p-3 transition-colors
                ${active
                  ? "border-ocean-500 bg-ocean-50 ring-1 ring-ocean-300"
                  : citation.was_cited
                    ? "border-slate-200 bg-white hover:border-ocean-300"
                    // Offered to the model but never cited. Dimmed rather than
                    // hidden — "we searched this and it wasn't used" is
                    // information, and in aggregate it's a retrieval-precision
                    // signal.
                    : "border-slate-100 bg-slate-50/60 opacity-60 hover:opacity-100"}`}
            >
              <div className="flex items-start gap-2">
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold
                    ${active ? "bg-ocean-500 text-white" : "bg-slate-100 text-slate-600"}`}
                >
                  {citation.index}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-slate-900 leading-snug">
                    {citation.heading_path || citation.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className={`rounded px-1.5 py-px text-[10px] ring-1 ${style.className}`}>
                      {style.label}
                    </span>
                    {citation.doc_version && (
                      <span className="text-[10px] text-slate-400">{citation.doc_version}</span>
                    )}
                    {citation.effective_date && (
                      <span className="text-[10px] text-slate-400">
                        {citation.effective_date}
                      </span>
                    )}
                    {/* Flagged at INGESTION time (ADR-009), not guessed here.
                        The user should know a newer entry disagrees with this
                        page even when the answer already handled it. */}
                    {citation.is_contested && (
                      <span
                        className="rounded bg-amber-100 px-1.5 py-px text-[10px] text-amber-800 ring-1 ring-amber-200"
                        title="A newer changelog entry contradicts part of this source."
                      >
                        superseded in part
                      </span>
                    )}
                    {!citation.was_cited && (
                      <span className="text-[10px] text-slate-400">not cited</span>
                    )}
                  </div>

                  {active && (
                    <div className="mt-2.5 border-t border-ocean-200 pt-2.5">
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">
                        {citation.source_path}
                      </p>
                      {/* Claims that cited THIS source, with the validator's
                          verdict. This is the actual "verified" in the
                          tagline, made inspectable. */}
                      {report?.claims
                        .filter((claim) => claim.cited_indices.includes(citation.index))
                        .map((claim, i) => (
                          <div
                            key={i}
                            className={`mb-1.5 rounded px-2 py-1.5 text-[11px] leading-snug
                              ${claim.supported
                                ? "bg-emerald-50 text-emerald-900"
                                : "bg-rose-50 text-rose-900"}`}
                          >
                            <span className="font-medium">
                              {claim.supported ? "✓ supports" : "✗ weak match"}
                            </span>
                            {claim.similarity != null && (
                              <span className="ml-1 opacity-60 tabular-nums">
                                ({claim.similarity.toFixed(2)})
                              </span>
                            )}
                            <p className="mt-0.5 opacity-80">
                              {claim.claim.slice(0, 140)}
                              {claim.claim.length > 140 ? "…" : ""}
                            </p>
                          </div>
                        ))}
                      <p className="text-[11px] text-slate-500">
                        retrieval score{" "}
                        <span className="tabular-nums">{citation.score.toFixed(3)}</span>
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {report && report.invalid_indices.length > 0 && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
            <p className="text-[12px] font-medium text-rose-800">
              Fabricated citations: {report.invalid_indices.join(", ")}
            </p>
            <p className="mt-1 text-[11px] text-rose-700">
              The answer referenced sources that were never provided to the model. Flagged
              rather than hidden — the answer may still be correct, and you should be able
              to see the discrepancy.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
