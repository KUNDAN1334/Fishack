"use client";

/**
 * The input row: tenant switcher, reset, textarea, and send/stop.
 *
 * The textarea grows with its content up to a cap. A fixed one-line input makes
 * people second-guess writing a real question — and a real question is exactly
 * the input a retrieval system works best on, because it carries more terms for
 * the keyword leg and more signal for the embedding.
 */

import { useEffect, useRef } from "react";

import { ArrowUp, RefreshCw, Square } from "@/components/ui/Icon";
import TenantSwitcher from "./TenantSwitcher";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  tenant: string;
  onTenantChange: (tenant: string) => void;
  onReset: () => void;
  hasHistory: boolean;
}

export default function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  tenant,
  onTenantChange,
  onReset,
  hasHistory,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Reset to `auto` first: without it, `scrollHeight` reports the height the
    // box already has, so the textarea can grow but never shrink again.
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value]);

  return (
    <div className="shrink-0 border-t border-line bg-surface px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <TenantSwitcher
            tenant={tenant}
            onChange={onTenantChange}
            disabled={busy}
            hasHistory={hasHistory}
          />

          <button
            type="button"
            onClick={onReset}
            disabled={busy || !hasHistory}
            className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-slate-500
                       transition-colors hover:bg-slate-100 hover:text-slate-800 disabled:opacity-40
                       disabled:hover:bg-transparent"
          >
            <RefreshCw size={12} />
            New conversation
          </button>

          {hasHistory && (
            <span className="text-xs text-slate-400">
              follow-ups are rewritten into standalone questions before search
            </span>
          )}
        </div>

        <div className="flex items-end gap-2 rounded-xl border border-line-strong bg-surface p-1.5
                        focus-within:border-ocean-400 focus-within:ring-2 focus-within:ring-ocean-500/25">
          <label htmlFor="composer-input" className="sr-only">
            Ask a question about Flowlytics
          </label>
          <textarea
            id="composer-input"
            ref={ref}
            rows={1}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter newlines — the convention every chat
              // UI uses, so it needs no explaining.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!busy && value.trim()) onSubmit();
              }
            }}
            placeholder="Ask about webhooks, rate limits, billing…"
            className="flex-1 resize-none bg-transparent px-2.5 py-1.5 text-sm leading-relaxed
                       text-slate-800 placeholder:text-slate-400 focus:outline-none"
          />

          {busy ? (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong
                         px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50"
            >
              <Square size={12} />
              Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={onSubmit}
              disabled={!value.trim()}
              aria-label="Send question"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ocean-600
                         text-white transition-colors hover:bg-ocean-700
                         disabled:bg-slate-200 disabled:text-slate-400"
            >
              <ArrowUp size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
