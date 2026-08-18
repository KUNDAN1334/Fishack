"use client";

/** Input box, tenant switcher, and the example prompts. */

import { useEffect, useRef } from "react";

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

const TENANTS = ["acme", "globex"];

export default function Composer({
  value, onChange, onSubmit, onStop, busy,
  tenant, onTenantChange, onReset, hasHistory,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with content up to a cap. A fixed one-line input makes people
  // second-guess writing a real question, which is exactly the input a
  // retrieval system works best on.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  return (
    <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex items-center gap-2 text-xs">
          {/* The tenant switcher IS the multi-tenancy demo. Ask the same
              question as each tenant and the private docs differ — which is
              what the isolation work in Phase 2 exists to guarantee.
              PRODUCTION NOTE: in a real deployment tenant comes from the
              authenticated session, never from a dropdown the user controls. */}
          <label className="text-slate-500">Tenant</label>
          <select
            value={tenant}
            onChange={(e) => onTenantChange(e.target.value)}
            disabled={busy}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-slate-700
                       focus:border-ocean-500 focus:outline-none disabled:opacity-50"
          >
            {TENANTS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <span className="text-slate-300">|</span>
          <button
            onClick={onReset}
            disabled={busy || !hasHistory}
            className="text-slate-500 hover:text-slate-800 disabled:opacity-40"
          >
            New conversation
          </button>
          {hasHistory && (
            <span className="text-slate-400">
              follow-ups are rewritten into standalone questions before search
            </span>
          )}
        </div>

        <div className="flex items-end gap-2">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends, Shift+Enter newlines — the convention every chat
              // UI uses, so it needs no explaining.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!busy && value.trim()) onSubmit();
              }
            }}
            placeholder="Ask about webhooks, rate limits, billing…"
            className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm
                       leading-relaxed placeholder:text-slate-400
                       focus:border-ocean-500 focus:outline-none focus:ring-1 focus:ring-ocean-300"
          />
          {busy ? (
            <button
              onClick={onStop}
              className="shrink-0 rounded-lg border border-slate-300 px-4 py-2 text-sm
                         text-slate-600 hover:bg-slate-50"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={onSubmit}
              disabled={!value.trim()}
              className="shrink-0 rounded-lg bg-ocean-600 px-4 py-2 text-sm font-medium text-white
                         hover:bg-ocean-700 disabled:bg-slate-200 disabled:text-slate-400"
            >
              Ask
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
