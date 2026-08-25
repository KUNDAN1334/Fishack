/**
 * Callouts.
 *
 * Five kinds, and the set is closed on purpose. Each maps to a colour from the
 * contract in `globals.css`, and each answers a different question, so a reader
 * learns to skim for the one they care about:
 *
 *   note        context that helps but is not required to proceed        slate
 *   caution     something that will bite you if you skip it              amber
 *   caveat      a limit on a number or claim stated nearby               amber
 *   production  what a production system would do differently            ocean
 *   result      a measured finding worth stopping on                     emerald
 *
 * `caveat` deserves its own kind rather than being a `note`. Almost every
 * measurement on this site has a condition that bounds it, and burying those in
 * body text is how a result about one 65-case synthetic corpus gets quoted as a
 * result about retrieval in general.
 *
 * Note what is NOT here: an "error" or "danger" kind in rose. Rose is reserved
 * for citation-validation failures in the product UI, and a documentation page
 * shouting in the same colour would dilute the one place it means something.
 */

import type { ReactNode } from "react";
import { AlertTriangle, Check, Info, Layers, ShieldCheck } from "@/components/ui/Icon";

export type CalloutKind = "note" | "caution" | "caveat" | "production" | "result";

const STYLES: Record<
  CalloutKind,
  { label: string; wrap: string; head: string; icon: ReactNode }
> = {
  note: {
    label: "Note",
    wrap: "border-line bg-surface-sunken",
    head: "text-slate-700",
    icon: <Info size={15} />,
  },
  caution: {
    label: "Caution",
    wrap: "border-amber-200 bg-amber-50",
    head: "text-amber-800",
    icon: <AlertTriangle size={15} />,
  },
  caveat: {
    label: "Caveat",
    wrap: "border-amber-200 bg-amber-50/60",
    head: "text-amber-800",
    icon: <AlertTriangle size={15} />,
  },
  production: {
    label: "In production",
    wrap: "border-ocean-200 bg-ocean-50/70",
    head: "text-ocean-800",
    icon: <Layers size={15} />,
  },
  result: {
    label: "Measured",
    wrap: "border-emerald-200 bg-emerald-50/70",
    head: "text-emerald-800",
    icon: <Check size={15} />,
  },
};

export default function Callout({
  kind = "note",
  title,
  children,
}: {
  kind?: CalloutKind;
  /** Overrides the kind's default label. Use for a specific finding. */
  title?: string;
  children: ReactNode;
}) {
  const style = STYLES[kind];

  return (
    <aside className={`!mt-6 rounded-lg border px-4 py-3.5 ${style.wrap}`}>
      <p className={`flex items-center gap-2 text-sm font-semibold ${style.head}`}>
        <span className="shrink-0">{style.icon}</span>
        {title ?? style.label}
      </p>
      <div className="mt-1.5 space-y-2 text-sm leading-relaxed text-slate-700 [&_a]:text-ocean-700 [&_a]:underline [&_a]:underline-offset-2">
        {children}
      </div>
    </aside>
  );
}

/**
 * The tenant-isolation callout, which appears on several pages and must say the
 * same thing every time. Extracted so it cannot drift between them.
 */
export function IsolationNote() {
  return (
    <aside className="!mt-6 rounded-lg border border-ocean-200 bg-ocean-50/70 px-4 py-3.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-ocean-800">
        <ShieldCheck size={15} />
        Isolation applies here too
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-slate-700">
        Every database read on this path goes through a <code>TenantScope</code> that owns the{" "}
        <code>FROM</code> clause and welds on <code>WHERE tenant_id = $1 AND is_current</code>.
        There is no code path that reads <code>chunks</code> without it, and a row that surfaces
        outside its tenant raises rather than being filtered away.
      </p>
    </aside>
  );
}
