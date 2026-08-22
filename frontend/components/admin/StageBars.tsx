/**
 * Mean latency per pipeline stage, as bars.
 *
 * This exists to make one finding impossible to miss: the cross-encoder owns
 * p95. On this hardware it is 1.7-3.3 seconds against a target of under three
 * seconds for the entire request, and it is both the one stage worth optimising
 * and the first thing to drop under load. A five-card grid of numbers stated
 * that and buried it; a bar chart states it in the shape.
 *
 * Plain CSS widths, no charting library. Four bars scaled to the slowest one
 * does not need 40 KB of JavaScript, and a `<div>` with a width is legible in
 * the DOM inspector, which a canvas is not.
 *
 * Honest label, because it matters: these are MEANS. Per-stage percentiles are
 * not recorded, so a single slow request moves a bar in a way it would not move
 * a p95. The shape is the finding; the individual numbers are not.
 */

const STAGE_TONE: Record<string, string> = {
  rerank: "bg-amber-400",
  generation: "bg-ocean-400",
  retrieval: "bg-ocean-300",
  rewrite: "bg-slate-300",
};

export default function StageBars({
  stages,
}: {
  stages: { name: string; ms: number }[];
}) {
  const slowest = Math.max(1, ...stages.map((stage) => stage.ms));

  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-4">
      <ul className="space-y-2.5">
        {stages.map((stage) => (
          <li key={stage.name} className="grid grid-cols-[6.5rem_minmax(0,1fr)_4.5rem] items-center gap-3">
            <span className="text-xs text-slate-600">{stage.name}</span>
            <span className="h-2 overflow-hidden rounded-full bg-slate-100">
              <span
                className={`block h-full rounded-full ${STAGE_TONE[stage.name] ?? "bg-slate-300"}`}
                style={{ width: `${Math.max(1.5, (stage.ms / slowest) * 100)}%` }}
              />
            </span>
            <span className="figure text-right text-xs text-slate-700">
              {stage.ms >= 1000 ? `${(stage.ms / 1000).toFixed(2)}s` : `${Math.round(stage.ms)}ms`}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 border-t border-line pt-2.5 text-xs leading-relaxed text-slate-500">
        Means, not percentiles — per-stage percentiles are not recorded. Bars are scaled to the
        slowest stage, so the shape is the finding rather than any single number.
      </p>
    </div>
  );
}
