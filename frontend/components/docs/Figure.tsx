/**
 * A wrapper for diagrams.
 *
 * Two responsibilities that every diagram on the site would otherwise have to
 * remember: a caption saying what the picture is claiming, and a horizontal
 * scroll container so a wide diagram never makes the page body scroll sideways
 * on a phone.
 *
 * The caption is not optional. A diagram without one is decoration — the reader
 * has to reverse-engineer what they are meant to take from it, and on a system
 * page that is exactly the work the documentation exists to do for them.
 */

import type { ReactNode } from "react";

export default function Figure({
  caption,
  children,
  /** Set when the diagram is legible without a border — e.g. it draws its own. */
  bare = false,
}: {
  caption: ReactNode;
  children: ReactNode;
  bare?: boolean;
}) {
  return (
    <figure className="!mt-6">
      <div
        className={`thin-scroll overflow-x-auto ${
          bare ? "" : "rounded-lg border border-line bg-surface p-4 sm:p-6"
        }`}
      >
        {children}
      </div>
      <figcaption className="mt-2 text-xs leading-relaxed text-slate-500">{caption}</figcaption>
    </figure>
  );
}
