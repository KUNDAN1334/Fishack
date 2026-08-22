"use client";

/**
 * The sources panel (ADR-028, Design.md §13e).
 *
 * Always visible, never behind a click. Two reasons:
 *
 *   1. The backend sends its `meta` event — the numbered citations — BEFORE
 *      the first token of the answer. So the sources render while the answer
 *      is still typing, and the reader watches it being built out of documents
 *      they can already see. That event ordering was designed for this, and it
 *      is the most interesting thing the UI does.
 *   2. The product's claim is "every claim cited, every citation verified".
 *      Evidence behind a click is evidence most people never look at, which
 *      makes the claim unfalsifiable in practice.
 *
 * The redesign closes ADR-028's stated gap. The panel used to be `hidden
 * lg:flex` — below 1024px the evidence simply disappeared, which is the wrong
 * thing for a phone reader to lose. It now has a fixed 380px rail on `lg` and
 * a slide-over sheet below it, opened from a button in the conversation header
 * that carries the source count.
 *
 * The sheet is a plain fixed-position panel with a scrim, not a portal-based
 * dialog. It closes on Escape, on scrim click, and on route change; focus moves
 * to its close button on open and back to the trigger on close. That is the
 * whole contract a dialog owes, at a tenth of the machinery.
 */

import { useEffect, useRef } from "react";

import type { Citation, CitationReport } from "@/lib/types";
import { Close, FileText } from "@/components/ui/Icon";
import SourceList from "./SourceList";

interface Props {
  citations: Citation[];
  report: CitationReport | null | undefined;
  activeIndex: number | null;
  onSelect: (index: number | null) => void;
  streaming: boolean;
  /** Mobile sheet state, owned by the page so the trigger can live in its header. */
  sheetOpen: boolean;
  onCloseSheet: () => void;
}

/** The panel's own header: how many sources, and how validation went. */
function PanelHeader({
  citations,
  report,
}: {
  citations: Citation[];
  report: CitationReport | null | undefined;
}) {
  const cited = citations.filter((c) => c.was_cited).length;
  const unsupported = report?.claims.filter((c) => !c.supported) ?? [];

  return (
    <div className="shrink-0 border-b border-line px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Sources</h2>
        <span className="figure text-xs text-slate-400">
          {cited} of {citations.length} cited
        </span>
      </div>
      {report && report.claims.length > 0 && (
        <p className="mt-1 text-xs">
          {unsupported.length === 0 ? (
            <span className="text-emerald-700">
              all <span className="figure">{report.claims.length}</span> claims matched the source
              they cited
            </span>
          ) : (
            <span className="text-rose-700">
              <span className="figure">{unsupported.length}</span> of{" "}
              <span className="figure">{report.claims.length}</span> claims could not be matched to
              their source
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Shown before the first `meta` event of the first question. */
function EmptyPanel({ streaming }: { streaming: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
      <FileText size={22} className="text-slate-300" />
      <p className="mt-3 text-sm font-medium text-slate-600">
        {streaming ? "Searching the corpus…" : "Sources appear here"}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
        Every answer shows the exact document chunks it was built from — with version, effective
        date, whether a newer entry contradicts them, and the validator&apos;s verdict on each
        claim.
      </p>
    </div>
  );
}

export default function CitationsPanel({
  citations,
  report,
  activeIndex,
  onSelect,
  streaming,
  sheetOpen,
  onCloseSheet,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Escape closes the sheet. Bound only while it is open, so the key is free
  // for the composer the rest of the time.
  useEffect(() => {
    if (!sheetOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseSheet();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen, onCloseSheet]);

  const body =
    citations.length === 0 ? (
      <EmptyPanel streaming={streaming} />
    ) : (
      <>
        <PanelHeader citations={citations} report={report} />
        <div className="thin-scroll flex-1 overflow-y-auto p-3">
          <SourceList
            citations={citations}
            report={report}
            activeIndex={activeIndex}
            onSelect={onSelect}
          />
        </div>
      </>
    );

  return (
    <>
      <aside
        aria-label="Sources"
        className="hidden w-[380px] shrink-0 flex-col border-l border-line bg-surface lg:flex"
      >
        {body}
      </aside>

      {sheetOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Sources">
          <button
            type="button"
            aria-label="Close sources"
            onClick={onCloseSheet}
            className="absolute inset-0 bg-slate-900/25 backdrop-blur-[1px]"
          />
          <div className="animate-sheet-in absolute inset-y-0 right-0 flex w-[min(24rem,92vw)] flex-col bg-surface shadow-pop">
            <div className="flex shrink-0 items-center justify-between border-b border-line px-4 py-3">
              <span className="text-sm font-semibold text-slate-900">Sources</span>
              <button
                ref={closeRef}
                type="button"
                onClick={onCloseSheet}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                <Close size={16} title="Close sources" />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col">{body}</div>
          </div>
        </div>
      )}
    </>
  );
}
