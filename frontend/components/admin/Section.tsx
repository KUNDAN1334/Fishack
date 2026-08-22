/**
 * A dashboard section, titled with the question it answers.
 *
 * The previous dashboard was a flat grid of numbers under generic headings —
 * "Latency", "Answer quality". Correct, and useless at a glance, because the
 * headings named the METRIC rather than the DECISION. An operator opening this
 * page has one of four questions, and each section is now named for one of
 * them: is it working, is it fast, is it trustworthy, is it leaking.
 *
 * The `hint` is where the section says how to read what follows — which
 * direction is bad, what the number is averaged over, what would make it lie.
 * That belongs beside the figures, not in a tooltip.
 */

import type { ReactNode } from "react";

export default function Section({
  id,
  question,
  hint,
  children,
}: {
  id: string;
  question: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-8 first:mt-0">
      <div className="mb-3">
        <h2 id={id} className="text-lg font-semibold tracking-tight text-slate-900">
          {question}
        </h2>
        {hint ? <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-500">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}
