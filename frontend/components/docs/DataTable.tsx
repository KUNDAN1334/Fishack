/**
 * Tables of measurements.
 *
 * Most of this documentation's load-bearing content is tabular — eval arms,
 * latency percentiles, tuning knobs, endpoint schemas — so the table is a real
 * component rather than raw `<table>` markup repeated twenty times.
 *
 * Three rules baked in, all of them about reading numbers rather than styling
 * them:
 *
 *   1. Numeric columns are right-aligned and set in the mono stack with
 *      tabular figures, so digits line up vertically and a reader can compare a
 *      column by scanning rather than by reading.
 *   2. A `highlight` row gets weight, not colour. The best arm in a comparison
 *      is worth marking; colouring it green would collide with the emerald that
 *      means "verified claim" everywhere else.
 *   3. The whole table scrolls horizontally inside its own container. A wide
 *      table must never make the page body scroll sideways on a phone.
 */

import type { ReactNode } from "react";

export interface Column {
  key: string;
  header: ReactNode;
  /** Right-aligns and applies tabular figures. Use for anything measured. */
  numeric?: boolean;
  /** Tailwind width hint, e.g. "w-[30%]". Optional. */
  width?: string;
}

export interface Row {
  /** Stable key. Usually the first cell's text. */
  id: string;
  cells: Record<string, ReactNode>;
  /** Weight, not colour — see rule 2 above. */
  highlight?: boolean;
  /** A quiet second line under the first cell, for provenance or a caveat. */
  note?: ReactNode;
}

export default function DataTable({
  columns,
  rows,
  caption,
}: {
  columns: Column[];
  rows: Row[];
  /** Rendered under the table as provenance: what produced these numbers. */
  caption?: ReactNode;
}) {
  return (
    <figure className="!mt-6">
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line bg-surface-sunken">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`px-3.5 py-2.5 text-2xs font-semibold uppercase tracking-[0.08em] text-slate-500 ${
                    column.numeric ? "text-right" : "text-left"
                  } ${column.width ?? ""}`}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => (
              <tr key={row.id} className={row.highlight ? "bg-ocean-50/40" : undefined}>
                {columns.map((column, index) => (
                  <td
                    key={column.key}
                    className={`px-3.5 py-2.5 align-top ${
                      column.numeric ? "figure text-right text-slate-700" : "text-slate-700"
                    } ${row.highlight ? "font-medium text-slate-900" : ""}`}
                  >
                    {row.cells[column.key]}
                    {index === 0 && row.note ? (
                      <span className="mt-0.5 block text-xs font-normal text-slate-400">
                        {row.note}
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {caption ? (
        <figcaption className="mt-2 text-xs leading-relaxed text-slate-500">{caption}</figcaption>
      ) : null}
    </figure>
  );
}
