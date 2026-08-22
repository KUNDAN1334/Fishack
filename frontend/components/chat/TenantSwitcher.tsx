"use client";

/**
 * The tenant switcher.
 *
 * This control IS the multi-tenancy demonstration: ask the same question as
 * each tenant and the private documents differ, which is what the isolation
 * work exists to guarantee.
 *
 * It states its own consequence. Switching tenant CLEARS the conversation,
 * because carrying history across would feed one tenant's answers into
 * another's prompt as context — not a chunk leak, but a leak. Doing that
 * silently would be the more convenient design and the less honest one, so the
 * menu says it before the click rather than after.
 *
 * PRODUCTION NOTE: in a real deployment the tenant comes from the authenticated
 * session or a JWT claim and is never accepted from a control the user
 * operates. `TenantScope` would be constructed from the auth context; nothing
 * below it in the pipeline changes.
 */

import { useEffect, useRef, useState } from "react";

import { Building, Check, ChevronDown } from "@/components/ui/Icon";

const TENANTS = [
  { id: "acme", note: "Enterprise plan · SSO and SCIM docs" },
  { id: "globex", note: "Growth plan · a different private corpus" },
];

export default function TenantSwitcher({
  tenant,
  onChange,
  disabled,
  hasHistory,
}: {
  tenant: string;
  onChange: (tenant: string) => void;
  disabled?: boolean;
  /** Drives whether the destructive consequence is worth stating. */
  hasHistory: boolean;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click and on Escape. `mousedown` rather than `click` so
  // the menu is gone before the click lands on whatever is underneath it.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1
                   text-xs text-slate-700 transition-colors hover:border-line-strong disabled:opacity-50"
      >
        <Building size={12} className="text-slate-400" />
        <span className="font-medium">{tenant}</span>
        <ChevronDown size={12} className="text-slate-400" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-30 mb-1.5 w-72 rounded-lg border border-line
                     bg-surface p-1 shadow-pop"
        >
          {TENANTS.map((option) => (
            <button
              key={option.id}
              role="menuitemradio"
              aria-checked={option.id === tenant}
              onClick={() => {
                setOpen(false);
                if (option.id !== tenant) onChange(option.id);
              }}
              className="flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left
                         transition-colors hover:bg-slate-50"
            >
              <span className="mt-0.5 w-3.5 shrink-0 text-ocean-600">
                {option.id === tenant ? <Check size={14} /> : null}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-slate-900">{option.id}</span>
                <span className="block text-xs text-slate-500">{option.note}</span>
              </span>
            </button>
          ))}

          {hasHistory && (
            <p className="mt-1 border-t border-line px-2.5 pb-1 pt-2 text-xs leading-relaxed text-amber-800">
              Switching clears this conversation. Carrying history across tenants would feed one
              tenant&apos;s answers into another&apos;s prompt.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
