/**
 * One headline figure.
 *
 * `tone` is applied only where a value genuinely has a good direction, and even
 * then it colours the number, never the card — a wall of tinted cards makes
 * every metric look like an alarm and none of them readable.
 *
 * `note` is where the figure's meaning lives: what it is over, which direction
 * is bad, and what would make it misleading. It used to be a `title=` tooltip,
 * which is invisible on touch, unreachable by keyboard, and unstyled — for
 * content this load-bearing that is the same as not writing it.
 */

import type { ReactNode } from "react";

export type Tone = "neutral" | "good" | "warn" | "bad";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "text-slate-900",
  good: "text-emerald-700",
  warn: "text-amber-700",
  bad: "text-rose-700",
};

export default function MetricCard({
  label,
  value,
  note,
  tone = "neutral",
  /** Renders a compact variant for dense rows of five or more. */
  compact = false,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: Tone;
  compact?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3.5">
      <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">{label}</p>
      <p
        className={`figure mt-1 font-semibold ${compact ? "text-xl" : "text-2xl"} ${TONE_CLASS[tone]}`}
      >
        {value}
      </p>
      {note ? <p className="mt-1 text-xs leading-relaxed text-slate-500">{note}</p> : null}
    </div>
  );
}

/** Formats a rate as a percentage with one decimal, or an em dash when undefined. */
export function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/** Milliseconds, promoted to seconds past 1,000 so a p95 is readable at a glance. */
export function ms(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}
