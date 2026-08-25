/**
 * The retrieval fan-out.
 *
 * The picture exists to make three things obvious that prose states badly:
 *
 *   1. The two legs run CONCURRENTLY, on different indexes and different
 *      pooled connections, so hybrid retrieval costs roughly max(bm25, vector)
 *      rather than their sum.
 *   2. Neither leg writes a full query. Both hand a fragment to `TenantScope`,
 *      which owns the `FROM` clause — so isolation is drawn as a band both
 *      legs pass through, not as a filter one of them remembers to apply.
 *   3. Fusion needs no hydration step. Both legs return full rows, so merging
 *      is a set union over objects already in memory rather than a second
 *      round trip to re-fetch the winners.
 */

export default function RetrievalDiagram() {
  return (
    <svg
      viewBox="0 0 900 348"
      className="w-full min-w-[620px]"
      role="img"
      aria-labelledby="retrieval-diagram-title retrieval-diagram-desc"
    >
      <title id="retrieval-diagram-title">The retrieval pipeline</title>
      <desc id="retrieval-diagram-desc">
        A query and a tenant scope enter. The query is embedded, then two legs run concurrently: a
        BM25 keyword leg using a generated tsvector column with a GIN index and cover-density
        ranking, and a vector leg using an HNSW index over 384-dimension embeddings. Both legs
        pass through TenantScope, which welds the tenant predicate onto every read and re-checks
        every returned row. Their ranked lists are merged by reciprocal rank fusion with k equal
        to 60 into twenty candidates. The top eight reach a cross-encoder reranker, which emits
        the top five. The result carries both the reranked results and the pre-rerank candidates,
        per-leg timings, and any degraded legs.
      </desc>

      <defs>
        <marker
          id="ret-arrow"
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

      {/* input */}
      <rect x="16" y="128" width="132" height="56" rx="8" className="fill-white stroke-line" />
      <text x="30" y="150" className="fill-slate-900 text-[12.5px] font-semibold">
        query + scope
      </text>
      <text x="30" y="167" className="fill-slate-500 font-mono text-[9.5px]">
        embed once, L2-normalised
      </text>

      <path d="M148 156 H186" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />

      {/* the two legs */}
      <rect x="186" y="66" width="196" height="66" rx="8" className="fill-white stroke-line" />
      <text x="202" y="88" className="fill-slate-900 text-[12.5px] font-semibold">
        Keyword leg
      </text>
      <text x="202" y="105" className="fill-slate-500 font-mono text-[9.5px]">
        websearch_to_tsquery, AND→OR
      </text>
      <text x="202" y="120" className="fill-slate-500 font-mono text-[9.5px]">
        ts_rank_cd over a GIN index
      </text>

      <rect x="186" y="180" width="196" height="66" rx="8" className="fill-white stroke-line" />
      <text x="202" y="202" className="fill-slate-900 text-[12.5px] font-semibold">
        Vector leg
      </text>
      <text x="202" y="219" className="fill-slate-500 font-mono text-[9.5px]">
        SET LOCAL hnsw.ef_search = 100
      </text>
      <text x="202" y="234" className="fill-slate-500 font-mono text-[9.5px]">
        embedding &lt;=&gt; query, HNSW
      </text>

      <path d="M170 156 V99 H184" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />
      <path d="M170 156 V213 H184" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />
      {/* Two short lines rather than one long one: SVG does not wrap, so a
          sentence long enough to be worth saying will run through whatever is
          to its right — here, the isolation band. */}
      <text x="196" y="152" className="fill-slate-400 font-mono text-[9.5px]">
        run concurrently —
      </text>
      <text x="196" y="164" className="fill-slate-400 font-mono text-[9.5px]">
        cost is max(legs)
      </text>

      {/* isolation band */}
      <rect x="404" y="52" width="120" height="208" rx="10" className="fill-ocean-50 stroke-ocean-300" />
      <text x="464" y="120" textAnchor="middle" className="fill-ocean-800 text-[12.5px] font-semibold">
        TenantScope
      </text>
      <text x="464" y="140" textAnchor="middle" className="fill-ocean-700 font-mono text-[9px]">
        owns FROM chunks
      </text>
      <text x="464" y="155" textAnchor="middle" className="fill-ocean-700 font-mono text-[9px]">
        WHERE tenant_id = $1
      </text>
      <text x="464" y="170" textAnchor="middle" className="fill-ocean-700 font-mono text-[9px]">
        AND is_current
      </text>
      <text x="464" y="192" textAnchor="middle" className="fill-ocean-600 font-mono text-[9px]">
        + foreign-row tripwire
      </text>

      <path d="M382 99 H402" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />
      <path d="M382 213 H402" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />

      {/* fusion */}
      <rect x="546" y="128" width="150" height="56" rx="8" className="fill-white stroke-line" />
      <text x="560" y="150" className="fill-slate-900 text-[12.5px] font-semibold">
        RRF fusion
      </text>
      <text x="560" y="167" className="fill-slate-500 font-mono text-[9.5px]">
        Σ w / (60 + rank) → top 20
      </text>
      <path d="M524 156 H544" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />

      {/* rerank */}
      <rect x="718" y="128" width="166" height="56" rx="8" className="fill-white stroke-line" />
      <text x="732" y="150" className="fill-slate-900 text-[12.5px] font-semibold">
        Cross-encoder
      </text>
      <text x="732" y="167" className="fill-slate-500 font-mono text-[9.5px]">
        top 8 in → sigmoid → top 5
      </text>
      <path d="M696 156 H716" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />

      {/* the bypass */}
      <path
        d="M621 128 V88 H801 V126"
        className="stroke-amber-300"
        fill="none"
        strokeDasharray="4 3"
      />
      <text x="560" y="64" className="fill-amber-700 font-mono text-[9.5px]">
        conditional rerank: margin ≥ 0.10 skips this
      </text>
      <text x="560" y="76" className="fill-amber-700 font-mono text-[9.5px]">
        implemented — and it never fires on this corpus
      </text>

      {/* output */}
      <rect x="546" y="272" width="338" height="58" rx="8" className="fill-surface-sunken stroke-line" />
      <text x="562" y="294" className="fill-slate-900 text-[12.5px] font-semibold">
        RetrievalResult
      </text>
      <text x="562" y="311" className="fill-slate-500 font-mono text-[9.5px]">
        results · candidates · per-leg timings · degraded_legs
      </text>
      <path d="M801 184 V250 H715 V270" className="stroke-slate-300" markerEnd="url(#ret-arrow)" fill="none" />
      <text x="562" y="244" className="fill-slate-400 font-mono text-[9.5px]">
        both lists are kept — see field note 2
      </text>
    </svg>
  );
}
