import type { Metadata } from "next";
import Link from "next/link";

import Callout, { IsolationNote } from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Figure from "@/components/docs/Figure";
import SystemDiagram from "@/components/docs/diagrams/SystemDiagram";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/architecture")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function ArchitecturePage() {
  return (
    <DocPage
      href="/docs/architecture"
      eyebrow="Architecture"
      title="System architecture"
      lead="Four planes — request, query, data, and the offline systems that feed them. Every component is written out rather than assembled from a framework, and every tuning knob has a recorded provenance saying whether its value was measured or guessed."
    >
      <Figure caption="The whole system. Ingestion and the evaluation harness sit underneath because they feed the pipeline rather than serving it: one produces the corpus the query path reads, the other produces the scorecard that says whether a change made it worse.">
        <SystemDiagram />
      </Figure>

      <H2 id="shape">The shape of the system</H2>
      <p>
        Fishack is one FastAPI application, one Next.js application, Postgres with pgvector, Redis,
        and two local transformer models. It is deliberately not a set of services: at this size a
        service boundary buys deployment independence nobody needs and costs a network hop, a
        serialisation format, and a failure mode on every call.
      </p>

      <DataTable
        columns={[
          { key: "component", header: "Component", width: "w-[26%]" },
          { key: "role", header: "Role" },
          { key: "note", header: "Notable" },
        ]}
        rows={[
          {
            id: "next",
            cells: {
              component: <>Next.js App Router</>,
              role: "Documentation, the assistant, and the operations dashboard",
              note: "Proxies every API call server-side, so the browser only ever talks to one origin and no CORS middleware exists anywhere",
            },
          },
          {
            id: "fastapi",
            cells: {
              component: <>FastAPI</>,
              role: "The query path, feedback, and admin statistics",
              note: "Long-lived resources are built once in the lifespan context and read off app.state — no globals, so tests can build an app against fakes",
            },
          },
          {
            id: "pg",
            cells: {
              component: <>Postgres 16 + pgvector</>,
              role: "Documents, chunks, embeddings, traces, escalations, feedback",
              note: "One datastore serves BOTH retrieval legs, so one tenant predicate covers both and index consistency is guaranteed by a generated column",
            },
          },
          {
            id: "redis",
            cells: {
              component: <>Redis</>,
              role: "Answer cache, cache reverse index, provider quota counters",
              note: "Every call is wrapped: a Redis failure degrades to a cache miss rather than an error",
            },
          },
          {
            id: "models",
            cells: {
              component: <>Local models (CPU)</>,
              role: "bge-small embeddings, bge-reranker-base cross-encoder",
              note: "Loaded at startup, not on first request — so a missing model fails the deploy rather than the first customer",
            },
          },
          {
            id: "llm",
            cells: {
              component: <>LLM fallback chain</>,
              role: "Query rewriting, generation, and the eval judge",
              note: "Four providers behind one interface, each raw httpx. Order is configuration; a quota-exhausted provider fails over without sleeping",
            },
          },
        ]}
      />

      <H3 id="no-framework">Why there is no RAG framework</H3>
      <p>
        No LangChain, no LlamaIndex, no vendor SDKs. Retrieval, rank fusion, reranking, prompt
        assembly, citation validation, caching and evaluation are all written out, and every
        provider is raw <code>httpx</code>.
      </p>
      <p>
        The reason is not purity. It is that the interesting decisions in a RAG system are exactly
        the ones a framework makes for you: how two incomparable score scales get merged, what a
        confidence threshold is measured against, whether an abstention is cacheable, which query
        the cache is keyed on. Each of those has a defensible answer here, and each has an ADR
        recording the alternatives that were rejected.
      </p>

      <Callout kind="production">
        <p>
          A team shipping this would reasonably reach for a framework for the plumbing and keep the
          decisions. The parts worth owning are the ranking function, the isolation boundary, the
          gate, and the evaluation harness — everything else is glue.
        </p>
      </Callout>

      <H2 id="request-plane">The request plane</H2>
      <p>
        Every frontend call goes to a relative <code>/api/…</code> path, which the Next server
        rewrites onto FastAPI. Two consequences follow, and the second one is the real reason.
      </p>
      <p>
        First, there is no CORS anywhere in the system — same-origin requests skip the mechanism
        entirely. That matters more than usual here because the chat response is a{" "}
        <strong>stream</strong>, and CORS combined with streaming is genuinely unpleasant to debug:
        a missing or wrong header produces a stream that simply stops, with no useful error in
        either the browser console or the server log.
      </p>
      <p>
        Second, one environment variable covers two environments. In Docker the backend is{" "}
        <code>api:8000</code> on the compose network; locally it is <code>localhost:8000</code>.
        Only <code>API_ORIGIN</code> changes, it is read on the Next server, and it never reaches
        the browser — which has no idea the backend exists as a separate thing.
      </p>

      <Callout kind="note" title="One endpoint is not a rewrite">
        <p>
          <code>/api/admin/stats</code> is a route handler rather than a rewrite, because the admin
          token has to be attached to the <em>outgoing</em> request and a rewrite cannot do that. A
          route handler runs on the server, so it can read the secret and forward it — and the
          token never enters the client bundle, which for a secret is the same as publishing it.
          Route handlers take precedence over <code>afterFiles</code> rewrites, so this shadows the
          generic rule for exactly that path and nothing else.
        </p>
      </Callout>

      <H2 id="storage">Storage layout</H2>
      <p>
        Five tables and one cache, with the versioning columns on <code>documents</code> and the
        tenant column denormalised onto <code>chunks</code> so that the isolation predicate never
        needs a join.
      </p>

      <CodeBlock
        language="sql"
        filename="app/db/migrations/001_init.sql (shape)"
        code={`tenants
  id                text primary key

documents
  id                uuid primary key
  tenant_id         text  references tenants
  source_type       text        -- docs | changelog | ticket
  source_path       text
  doc_version       text
  effective_date    date
  content_hash      text        -- dedup: re-ingesting identical content is a no-op
  is_current        boolean     -- superseded documents are archived, never deleted

chunks
  id                uuid primary key
  document_id       uuid  references documents
  tenant_id         text        -- DENORMALISED: the isolation predicate never joins
  chunk_index       int
  content           text        -- heading path is prepended into this (ADR-004)
  heading_path      text
  metadata          jsonb       -- doc_version, product_area, error_code, conflicts_with_entry…
  embedding         vector(384) -- HNSW index
  tsv               tsvector    -- GENERATED from content; GIN index
  is_current        boolean
  unique (document_id, chunk_index)

embedding_cache     -- sha256(model + text) -> vector. Makes re-ingestion nearly free.
traces              -- one row per request, written after the response
escalations         -- one row per abstention, with history and the top 10 chunks + scores
feedback            -- thumbs, keyed by trace_id`}
      />

      <H3 id="why-denormalised">Why tenant_id is denormalised onto chunks</H3>
      <p>
        Because the isolation predicate is on the hot path of every single read, and a join is a
        thing a developer can forget to write. With <code>tenant_id</code> on the row, the scope
        that owns the <code>FROM</code> clause can weld the predicate on unconditionally, and the
        runtime tripwire that re-checks every returned row has something local to check against.
      </p>

      <IsolationNote />

      <H3 id="traces">What a trace row carries, and why</H3>
      <p>
        One row per request, written once <em>after</em> the response: the action taken, the
        confidence and <strong>which scale it is on</strong>, the retrieved chunk ids, the citation
        report as JSONB with its grounding rate precomputed, provider and model, tokens, virtual
        cost, and per-stage latencies. Writing traces never raises — an observability failure must
        not become a user-facing one.
      </p>
      <p>
        The score kind is on the row rather than inferred later because{" "}
        <code>top_score = 0.02</code> is uninterpretable six weeks after the fact. It is a healthy
        fusion score and a catastrophic reranker score, and a trace that cannot be read is not
        observability.
      </p>

      <H2 id="knobs">Every tuning knob, and where its value came from</H2>
      <p>
        The status column is the point of this table. A number that <em>looks</em> tuned and never
        was is worse than an obvious placeholder — one of them was wrong by 4x in the direction
        that made its own feature invisible, and it sat in configuration with a confident comment
        explaining its reasoning.
      </p>

      <DataTable
        columns={[
          { key: "setting", header: "Setting", width: "w-[27%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "status", header: "Provenance" },
          { key: "why", header: "Reasoning" },
        ]}
        rows={[
          {
            id: "candidates",
            cells: {
              setting: <code>retrieval_candidates_per_leg</code>,
              value: "20",
              status: "design",
              why: "Asking each leg for more than we keep is nearly free and gives fusion room to promote a chunk one leg ranked 18th and the other 2nd",
            },
          },
          {
            id: "fusion-top-k",
            cells: {
              setting: <code>retrieval_fusion_top_k</code>,
              value: "20",
              status: "design",
              why: "The candidate set that recall@20 is computed over",
            },
          },
          {
            id: "rerank-input",
            cells: {
              setting: <code>rerank_input_top_k</code>,
              value: "8",
              status: "measured",
              why: "The cross-encoder costs ~270 ms per pair on CPU. Eight instead of twenty is ~2.5x faster and retrieval is unaffected, because fusion still emits twenty",
            },
            highlight: true,
          },
          {
            id: "rerank-top-k",
            cells: {
              setting: <code>rerank_top_k</code>,
              value: "5",
              status: "design",
              why: "More context costs tokens, latency, and needle-in-haystack dilution",
            },
          },
          {
            id: "rrf-k",
            cells: {
              setting: <code>rrf_k</code>,
              value: "60",
              status: "literature",
              why: "Cormack et al. 2009. Damps rank 1 against rank 2 to under 2%, so one leg cannot steamroll the other",
            },
          },
          {
            id: "rrf-weights",
            cells: {
              setting: <code>rrf_weight_bm25 / _vector</code>,
              value: "1.0 / 1.0",
              status: "open question",
              why: "Weights were avoided on principle, then evaluation measured BM25 actively hurting multi-turn recall. 0.5 is the obvious next experiment and has not been run",
            },
          },
          {
            id: "ef-search",
            cells: {
              setting: <code>hnsw_ef_search</code>,
              value: "100",
              status: "design",
              why: "pgvector's default of 40 is too narrow once a selective tenant filter discards most of the beam",
            },
          },
          {
            id: "conditional",
            cells: {
              setting: <code>conditional_rerank_enabled</code>,
              value: "false",
              status: "deliberate",
              why: "Always-rerank is the quality ceiling the evaluation measures the gate against. Shipping the gate on would make the gated arm the baseline and delete the comparison",
            },
          },
          {
            id: "margin",
            cells: {
              setting: <code>rerank_margin_threshold</code>,
              value: "0.10",
              status: "measured, still not firing",
              why: "The original 0.30 was wrong by 4x. Real margins are 0.055–0.076, and even 0.10 never fires — so conditional reranking is implemented and not yet demonstrated to do anything on this corpus",
            },
            highlight: true,
          },
          {
            id: "conf-rerank",
            cells: {
              setting: <code>confidence_threshold_rerank</code>,
              value: "0.45",
              status: "guess",
              why: "Provisional and labelled so. `make tune` sweeps it against the golden set",
            },
          },
          {
            id: "conf-fused",
            cells: {
              setting: <code>confidence_threshold_fused</code>,
              value: "0.015",
              status: "guess",
              why: "Separate from the above because the two scales differ by roughly 30x",
            },
          },
          {
            id: "semantic",
            cells: {
              setting: <code>semantic_cache_threshold</code>,
              value: "0.95",
              status: "design + guardrails",
              why: "Survivable only because identifier-bearing queries skip the semantic cache entirely and abstentions are never cached",
            },
          },
          {
            id: "citation",
            cells: {
              setting: <code>citation_similarity_threshold</code>,
              value: "0.50",
              status: "deliberate",
              why: "Lenient on purpose — it is catching UNRELATED citations, not grading paraphrase quality",
            },
          },
          {
            id: "ttl",
            cells: {
              setting: <code>cache_ttl_seconds</code>,
              value: "3600",
              status: "design",
              why: "Shorter than the freshness requirement. It is the backstop for bugs in active invalidation, not the primary mechanism",
            },
          },
        ]}
        caption="All of these live in app/config.py, which is the single place any constant, threshold or model name is allowed to exist. Model names are configuration rather than code because free-tier lineups change monthly."
      />

      <p>
        <Link href="/docs/configuration">
          The configuration reference lists every environment variable alongside these →
        </Link>
      </p>

      <H2 id="build-order">Build order</H2>
      <p>
        The system was built in seven phases, each of which had to be demonstrably working before
        the next began. The ordering is not arbitrary: infrastructure and the LLM client came
        first so that everything after could assume a working provider chain; the evaluation
        harness came <em>after</em> the pipeline so it had something real to score, and immediately
        contradicted two of the pipeline&apos;s design assumptions.
      </p>

      <DataTable
        columns={[
          { key: "phase", header: "Phase", width: "w-[16%]" },
          { key: "built", header: "What it added" },
          { key: "adrs", header: "Decisions", width: "w-[26%]" },
        ]}
        rows={[
          {
            id: "p0",
            cells: {
              phase: "0 · Foundations",
              built: "Schema and migrations, the four-provider LLM client with retries and failover, budget tracking, /health",
              adrs: "ADR-001, 002, 003, 005, 006",
            },
          },
          {
            id: "p1",
            cells: {
              phase: "1 · Ingestion",
              built: "Three loaders, three chunking strategies, cached embeddings, versioning and conflict tagging",
              adrs: "ADR-004, 008, 009, 010",
            },
          },
          {
            id: "p2",
            cells: {
              phase: "2 · Retrieval",
              built: "The keyword and vector legs, rank fusion, the cross-encoder, and the isolation core",
              adrs: "ADR-011, 012, 013, 014",
            },
          },
          {
            id: "p3",
            cells: {
              phase: "3 · Generation",
              built: "Query rewriting, the confidence gate, grounded generation, citation validation, escalations, traces",
              adrs: "ADR-015, 016, 017, 018",
            },
          },
          {
            id: "p4",
            cells: {
              phase: "4 · Evaluation",
              built: "The golden set, stable locators, the metrics, the LLM judge, the CI regression gate",
              adrs: "ADR-019, 020, 021, 022",
            },
          },
          {
            id: "p5",
            cells: {
              phase: "5 · Cache & feedback",
              built: "Exact and semantic caching, active invalidation, feedback triage, the admin statistics endpoint",
              adrs: "ADR-023, 024, 025, 026",
            },
          },
          {
            id: "p6",
            cells: {
              phase: "6 · Frontend",
              built: "The assistant, the operations dashboard, and this documentation site",
              adrs: "ADR-027, 028, 029",
            },
          },
        ]}
      />
    </DocPage>
  );
}
