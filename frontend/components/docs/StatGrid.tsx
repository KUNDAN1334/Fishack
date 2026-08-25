/**
 * A row of headline figures.
 *
 * The rule this component enforces is that a number never appears without its
 * provenance. `label` says what it is, `value` is the figure, and `note` says
 * where it came from — the command that produces it, the sample it is over, or
 * the condition that bounds it. `note` is required, not optional, because a
 * figure with no source is the exact thing this project's own field notes are
 * about: a threshold that looked tuned and had never been measured.
 *
 * Values are `figure` (mono, tabular) so a row of them aligns on the decimal.
 */

import type { ReactNode } from "react";

export interface Stat {
  label: string;
  value: ReactNode;
  /** Provenance. Required. See the note above. */
  note: ReactNode;
}

export default function StatGrid({
  stats,
  columns = 4,
}: {
  stats: Stat[];
  columns?: 2 | 3 | 4;
}) {
  const grid =
    columns === 2
      ? "sm:grid-cols-2"
      : columns === 3
        ? "sm:grid-cols-2 lg:grid-cols-3"
        : "sm:grid-cols-2 lg:grid-cols-4";

  return (
    <div className={`!mt-6 grid gap-px overflow-hidden rounded-lg border border-line bg-line ${grid}`}>
      {stats.map((stat) => (
        <div key={stat.label} className="bg-surface px-4 py-3.5">
          <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
            {stat.label}
          </p>
          <p className="figure mt-1.5 text-2xl font-semibold text-slate-900">{stat.value}</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{stat.note}</p>
        </div>
      ))}
    </div>
  );
}

/**
 * A pair of facing claims — what a component does, and what it deliberately
 * does not. Used on the overview and on pages where the honest boundary of a
 * feature is more informative than the feature.
 */
export function ContrastList({
  items,
}: {
  items: { claim: string; because: ReactNode }[];
}) {
  return (
    <dl className="!mt-6 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
      {items.map((item) => (
        <div key={item.claim} className="grid gap-1 px-4 py-3 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
          <dt className="text-sm font-medium text-slate-900">{item.claim}</dt>
          <dd className="text-sm leading-relaxed text-slate-600">{item.because}</dd>
        </div>
      ))}
    </dl>
  );
}
