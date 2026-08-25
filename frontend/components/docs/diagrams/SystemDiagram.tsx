/**
 * The one architecture picture the whole site refers back to.
 *
 * Drawn as inline SVG rather than rendered from Mermaid. Three reasons, in
 * order of weight: a Mermaid runtime is ~900 KB of JavaScript on a
 * documentation page; its automatic layout puts the boxes where the algorithm
 * likes rather than where the argument is; and the result is an image, so the
 * labels are invisible to search and to a screen reader. Inline SVG is text in
 * the DOM, styled by the same tokens as everything else, and it costs nothing
 * at runtime.
 *
 * The picture is arranged in four bands, and the arrangement IS the claim:
 * the request plane on top, the query pipeline in the middle, the data and
 * model plane below it, and the two offline systems — ingestion and the eval
 * harness — underneath everything, feeding it rather than serving it.
 *
 * Boxes are generated from arrays so that adding a stage is a one-line edit
 * and cannot leave a rectangle and its label out of sync.
 */

/**
 * The seven stages.
 *
 * `sub` is an explicit two-line array rather than a sentence that gets wrapped
 * at render time. SVG has no text wrapping, so anything that decides line breaks
 * by counting words will overflow its box the moment a label changes — which is
 * exactly what happened here. Each line is capped at 14 characters, which fits
 * a 116px box at 9.5px in the mono stack with room either side.
 */
const STAGES: { x: number; label: string; sub: [string, string] }[] = [
  { x: 34, label: "Rewrite", sub: ["follow-up →", "standalone"] },
  { x: 162, label: "Cache", sub: ["exact, then", "semantic"] },
  { x: 290, label: "Retrieve", sub: ["BM25 + vector", "→ RRF"] },
  { x: 418, label: "Rerank", sub: ["cross-encoder", "top 8 → 5"] },
  { x: 546, label: "Gate", sub: ["confidence", "threshold"] },
  { x: 674, label: "Generate", sub: ["closed-book,", "cited"] },
  { x: 802, label: "Validate", sub: ["per claim,", "post-hoc"] },
];

const STAGE_WIDTH = 116;

const DATA = [
  {
    x: 40,
    w: 250,
    label: "Postgres 16 + pgvector",
    sub: "chunks · documents · traces · escalations · feedback",
  },
  { x: 306, w: 190, label: "Redis", sub: "answer cache · quota counters" },
  {
    x: 512,
    w: 190,
    label: "Local models (CPU)",
    sub: "bge-small · bge-reranker-base",
  },
  {
    x: 718,
    w: 220,
    label: "LLM fallback chain",
    sub: "Groq → Gemini → OpenRouter → Ollama",
  },
];

export default function SystemDiagram() {
  return (
    <svg
      viewBox="0 0 978 566"
      className="w-full min-w-[720px]"
      role="img"
      aria-labelledby="system-diagram-title system-diagram-desc"
    >
      <title id="system-diagram-title">Fishack system architecture</title>
      <desc id="system-diagram-desc">
        Four bands. The request plane holds the chat UI and the operations dashboard, both served
        by Next.js. Below it, the FastAPI query pipeline runs seven stages in order: rewrite,
        cache, retrieve, rerank, confidence gate, generate, validate. Below that, the data and
        model plane holds Postgres with pgvector, Redis, the local embedding and reranker models,
        and the four-provider LLM fallback chain. Underneath, two offline systems feed the
        pipeline: the ingestion pipeline that loads, chunks, embeds and versions the corpus, and
        the fishnet evaluation harness that scores retrieval and generation against a 65-case
        golden set and gates CI.
      </desc>

      <defs>
        <marker
          id="sys-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0 0 10 5 0 10z" className="fill-slate-300" />
        </marker>
      </defs>

      {/* ---------------------------------------------- band 1 · request -- */}
      <text x="40" y="22" className="fill-slate-400 font-mono text-[10px] uppercase tracking-[0.14em]">
        Request plane · Next.js App Router
      </text>
      <rect x="40" y="32" width="250" height="48" rx="8" className="fill-white stroke-line" />
      <text x="56" y="53" className="fill-slate-900 text-[13px] font-semibold">
        Chat UI
      </text>
      <text x="56" y="69" className="fill-slate-500 font-mono text-[10.5px]">
        /try · streaming · sources panel
      </text>

      <rect x="306" y="32" width="230" height="48" rx="8" className="fill-white stroke-line" />
      <text x="322" y="53" className="fill-slate-900 text-[13px] font-semibold">
        Operations dashboard
      </text>
      <text x="322" y="69" className="fill-slate-500 font-mono text-[10.5px]">
        /admin · one row per request
      </text>

      <rect x="552" y="32" width="386" height="48" rx="8" className="fill-surface-sunken stroke-line" strokeDasharray="4 3" />
      <text x="568" y="53" className="fill-slate-700 text-[13px] font-semibold">
        Same-origin proxy — no CORS anywhere in the system
      </text>
      <text x="568" y="69" className="fill-slate-500 font-mono text-[10.5px]">
        next.config.mjs rewrites /api/* → FastAPI (ADR-027)
      </text>

      <path d="M165 80 V112" className="stroke-slate-300" markerEnd="url(#sys-arrow)" fill="none" />
      <path d="M421 80 V112" className="stroke-slate-300" markerEnd="url(#sys-arrow)" fill="none" />

      {/* ----------------------------------------------- band 2 · query -- */}
      <rect x="24" y="112" width="930" height="118" rx="12" className="fill-ocean-50/60 stroke-ocean-200" />
      <text x="40" y="132" className="fill-ocean-700 font-mono text-[10px] uppercase tracking-[0.14em]">
        Query path · FastAPI · app/generation/pipeline.py
      </text>

      {STAGES.map((stage, index) => (
        <g key={stage.label}>
          <rect
            x={stage.x}
            y={144}
            width={STAGE_WIDTH}
            height={64}
            rx={8}
            className="fill-white stroke-ocean-200"
          />
          <text x={stage.x + 11} y={166} className="fill-slate-900 text-[12.5px] font-semibold">
            {index + 1}. {stage.label}
          </text>
          <text x={stage.x + 11} y={182} className="fill-slate-500 font-mono text-[9.5px]">
            {stage.sub[0]}
          </text>
          <text x={stage.x + 11} y={195} className="fill-slate-500 font-mono text-[9.5px]">
            {stage.sub[1]}
          </text>
          {index < STAGES.length - 1 && (
            <path
              d={`M${stage.x + STAGE_WIDTH} 176 H${stage.x + 128}`}
              className="stroke-ocean-300"
              markerEnd="url(#sys-arrow)"
              fill="none"
            />
          )}
        </g>
      ))}

      {/* The two branches that leave the pipeline early. Drawn, because "it can
          decline to continue" is the product's whole thesis. Both labels start
          clear of their own dashed run so neither crosses a line. */}
      <path d="M220 208 V238 H286" className="stroke-amber-300" fill="none" strokeDasharray="4 3" markerEnd="url(#sys-arrow)" />
      <text x="294" y="242" className="fill-amber-700 font-mono text-[9.5px]">
        cache hit → answer in ~10 ms, zero LLM calls
      </text>
      <path d="M604 208 V238 H660" className="stroke-amber-300" fill="none" strokeDasharray="4 3" markerEnd="url(#sys-arrow)" />
      <text x="668" y="242" className="fill-amber-700 font-mono text-[9.5px]">
        below threshold → abstain
      </text>

      {/* ------------------------------------------------ band 3 · data -- */}
      <text x="40" y="286" className="fill-slate-400 font-mono text-[10px] uppercase tracking-[0.14em]">
        Data and model plane
      </text>
      {DATA.map((box) => (
        <g key={box.label}>
          <rect x={box.x} y={296} width={box.w} height={56} rx={8} className="fill-white stroke-line" />
          <text x={box.x + 14} y={318} className="fill-slate-900 text-[12.5px] font-semibold">
            {box.label}
          </text>
          <text x={box.x + 14} y={335} className="fill-slate-500 font-mono text-[9.5px]">
            {box.sub}
          </text>
        </g>
      ))}
      {/* Which stage reaches which store. These start below the branch labels
          rather than at the band edge, so no connector is drawn through text. */}
      {[220, 348, 476, 860].map((x) => (
        <path
          key={x}
          d={`M${x} 256 V296`}
          className="stroke-slate-300"
          markerEnd="url(#sys-arrow)"
          fill="none"
          strokeDasharray="3 3"
        />
      ))}

      {/* --------------------------------------------- band 4 · offline -- */}
      <text x="40" y="400" className="fill-slate-400 font-mono text-[10px] uppercase tracking-[0.14em]">
        Offline — feeds the system, never serves a request
      </text>

      <rect x="40" y="410" width="456" height="122" rx="10" className="fill-surface-sunken stroke-line" />
      <text x="56" y="432" className="fill-slate-900 text-[12.5px] font-semibold">
        Ingestion pipeline
      </text>
      <text x="56" y="452" className="fill-slate-600 font-mono text-[10px]">
        3 loaders → 3 chunking strategies → bge-small (cached)
      </text>
      <text x="56" y="468" className="fill-slate-600 font-mono text-[10px]">
        → transactional insert → second pass
      </text>
      <text x="56" y="490" className="fill-slate-500 font-mono text-[10px]">
        supersede a doc · tag chunks a newer entry contests
      </text>
      <text x="56" y="512" className="fill-slate-400 font-mono text-[10px]">
        idempotent by content hash · ~312 chunks, two tenants
      </text>

      <rect x="512" y="410" width="426" height="122" rx="10" className="fill-surface-sunken stroke-line" />
      <text x="528" y="432" className="fill-slate-900 text-[12.5px] font-semibold">
        fishnet — the evaluation harness
      </text>
      <text x="528" y="452" className="fill-slate-600 font-mono text-[10px]">
        65-case golden set → stable locators → recall@k · MRR
      </text>
      <text x="528" y="468" className="fill-slate-600 font-mono text-[10px]">
        → LLM judge on a separate model and provider chain
      </text>
      <text x="528" y="490" className="fill-slate-500 font-mono text-[10px]">
        → scorecard → CI gate against a committed baseline
      </text>
      <text x="528" y="512" className="fill-slate-400 font-mono text-[10px]">
        5% tolerance on quality · zero on correctness
      </text>

      <path d="M268 410 V360" className="stroke-slate-300" markerEnd="url(#sys-arrow)" fill="none" />
      <path d="M725 410 V360" className="stroke-slate-300" markerEnd="url(#sys-arrow)" fill="none" strokeDasharray="3 3" />
    </svg>
  );
}
