/**
 * An ordered sequence with a connecting rule.
 *
 * Used wherever order is the content — the eight stages of the query path, the
 * five queries in the guided tour, a deployment procedure. A plain `<ol>` would
 * carry the same semantics; the rule down the left is what makes a reader treat
 * it as one continuous process rather than a list of independent items, which
 * matters most on the query path where each stage can decline to hand work to
 * the next.
 *
 * Rendered as a real `<ol>` so a screen reader still announces "list, 8 items,
 * item 3" and the numbers are not decorative text.
 */

import type { ReactNode } from "react";

export interface Step {
  /** Short imperative or noun label. Becomes the bold line. */
  title: ReactNode;
  /** One or two sentences. What happens, and what it decides. */
  body: ReactNode;
  /** Optional right-hand annotation: a file path, a latency, a config key. */
  aside?: ReactNode;
}

export default function Steps({
  steps,
  /** `numbered` for a procedure; `plain` when the order matters but the count does not. */
  variant = "numbered",
}: {
  steps: Step[];
  variant?: "numbered" | "plain";
}) {
  return (
    <ol className="!mt-6 !space-y-0 !pl-0" style={{ listStyle: "none" }}>
      {steps.map((step, index) => {
        const last = index === steps.length - 1;
        return (
          <li key={index} className="relative flex gap-4 pb-6 last:pb-0">
            {/* The connector. Absolutely positioned so it runs behind the
                marker and stops at the final step rather than trailing off. */}
            {!last && (
              <span
                aria-hidden="true"
                className="absolute left-[13px] top-7 bottom-0 w-px bg-line"
              />
            )}

            <span
              aria-hidden="true"
              className={`relative z-10 mt-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center
                          rounded-full border text-2xs font-semibold ${
                            variant === "numbered"
                              ? "border-ocean-200 bg-ocean-50 text-ocean-700"
                              : "border-line bg-surface text-slate-400"
                          }`}
            >
              {variant === "numbered" ? index + 1 : "•"}
            </span>

            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                {step.aside ? (
                  <span className="figure text-2xs text-slate-400">{step.aside}</span>
                ) : null}
              </div>
              <div className="mt-1 text-sm leading-relaxed text-slate-600">{step.body}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
