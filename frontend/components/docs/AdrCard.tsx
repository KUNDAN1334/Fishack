/**
 * One architecture decision record.
 *
 * The shape enforces the record's own rule: context, decision, and the
 * alternatives that were rejected WITH the reason. A record whose entries can
 * omit their alternatives degenerates into a changelog — "we did X" is a fact,
 * not a decision, and the reasoning is the entire value.
 *
 * Rendered as a `<details>` so the index is scannable at a glance and any entry
 * expands in place. That also means Ctrl-F finds text inside collapsed entries
 * in most browsers, and it needs no JavaScript at all.
 */

import type { Adr } from "@/lib/adrs";
import { ChevronRight } from "@/components/ui/Icon";

export default function AdrCard({ adr }: { adr: Adr }) {
  return (
    <details
      id={adr.id}
      className="group scroll-mt-24 overflow-hidden rounded-lg border border-line bg-surface
                 open:shadow-card"
    >
      <summary
        className="flex cursor-pointer list-none items-start gap-3 px-4 py-3
                   transition-colors hover:bg-surface-sunken"
      >
        <ChevronRight
          size={14}
          className="mt-1 shrink-0 text-slate-400 transition-transform group-open:rotate-90"
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="figure text-2xs font-semibold text-ocean-600">{adr.id}</span>
            <span className="text-sm font-semibold text-slate-900">{adr.title}</span>
          </span>
        </span>
        <span className="mt-0.5 hidden shrink-0 rounded-sm bg-surface-sunken px-1.5 py-0.5 text-2xs text-slate-500 sm:inline">
          {adr.phase}
        </span>
      </summary>

      <div className="space-y-4 border-t border-line px-4 py-4 pl-[2.35rem]">
        <div>
          <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
            Context
          </p>
          <p className="text-sm leading-relaxed text-slate-600">{adr.context}</p>
        </div>

        <div>
          <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
            Decision
          </p>
          <p className="text-sm leading-relaxed text-slate-800">{adr.decision}</p>
        </div>

        <div>
          <p className="mb-1.5 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
            Alternatives considered, and why they were rejected
          </p>
          <ul className="space-y-2.5">
            {adr.alternatives.map((alternative) => (
              <li key={alternative.option} className="border-l-2 border-line pl-3">
                <p className="text-sm font-medium text-slate-700">{alternative.option}</p>
                <p className="mt-0.5 text-sm leading-relaxed text-slate-500">
                  {alternative.rejected}
                </p>
              </li>
            ))}
          </ul>
        </div>

        {adr.note && (
          <div className="rounded-md bg-surface-sunken px-3 py-2.5">
            <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
              Consequence
            </p>
            <p className="text-sm leading-relaxed text-slate-600">{adr.note}</p>
          </div>
        )}
      </div>
    </details>
  );
}
