import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/configuration")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function ConfigurationPage() {
  return (
    <DocPage
      href="/docs/configuration"
      eyebrow="Operations"
      title="Configuration"
      lead="Every constant, threshold and model name lives in one file, and each one carries a comment explaining how its value was chosen. That rule exists because a number that looks tuned and never was is worse than an obvious placeholder."
    >
      <H2 id="rule">The rule</H2>
      <p>
        No constant appears inline in code. Environment variables map to field names
        case-insensitively, so <code>DATABASE_URL</code> becomes <code>database_url</code>, and{" "}
        <code>.env.example</code> documents every one.
      </p>
      <p>
        Model names are configuration rather than code for a specific reason: free-tier lineups
        change monthly, and providers retire models with little notice. A 404 from a provider is a
        one-line fix in <code>.env</code> rather than a code change and a deploy.
      </p>

      <H2 id="infra">Infrastructure</H2>
      <DataTable
        columns={[
          { key: "var", header: "Variable", width: "w-[30%]" },
          { key: "default", header: "Default" },
          { key: "notes", header: "Notes" },
        ]}
        rows={[
          {
            id: "db",
            cells: {
              var: <code>DATABASE_URL</code>,
              default: "postgresql://fishack:fishack@localhost:5432/fishack",
              notes: "Needs the pgvector extension enabled",
            },
          },
          {
            id: "redis",
            cells: {
              var: <code>REDIS_URL</code>,
              default: "redis://localhost:6379/0",
              notes: "Use rediss:// for hosted Redis — Upstash requires TLS",
            },
          },
          {
            id: "admin",
            cells: {
              var: <code>ADMIN_TOKEN</code>,
              default: "(empty)",
              notes: "Empty means the statistics endpoint is OPEN. Set it before anything is public",
            },
            highlight: true,
          },
          {
            id: "origin",
            cells: {
              var: <code>API_ORIGIN</code>,
              default: "http://localhost:8000",
              notes: "Frontend only. Read on the Next server, never shipped to the browser",
            },
          },
        ]}
      />

      <H2 id="providers">LLM providers</H2>
      <DataTable
        columns={[
          { key: "var", header: "Variable", width: "w-[30%]" },
          { key: "default", header: "Default" },
          { key: "notes", header: "Notes" },
        ]}
        rows={[
          {
            id: "order",
            cells: {
              var: <code>LLM_PROVIDER_ORDER</code>,
              default: "groq,gemini,openrouter,ollama",
              notes:
                "First is primary, the rest are failover targets. Groq leads on the fastest inference and the most generous free request quota; Ollama is last because it is optional and slowest",
            },
            highlight: true,
          },
          { id: "groq", cells: { var: <code>GROQ_API_KEY / GROQ_MODEL</code>, default: "llama-3.1-8b-instant", notes: "The only required key" } },
          { id: "gem", cells: { var: <code>GOOGLE_API_KEY / GEMINI_MODEL</code>, default: "gemini-2.5-flash", notes: "Optional fallback" } },
          {
            id: "or",
            cells: {
              var: <code>OPENROUTER_API_KEY / OPENROUTER_MODEL</code>,
              default: "meta-llama/llama-3.3-70b-instruct:free",
              notes: "Optional fallback",
            },
          },
          {
            id: "ollama",
            cells: {
              var: <code>OLLAMA_ENABLED / OLLAMA_BASE_URL / OLLAMA_MODEL</code>,
              default: "false · localhost:11434 · llama3.1:8b",
              notes: "Fully offline, needs roughly 8 GB of RAM",
            },
          },
        ]}
      />

      <H3 id="retries">Retries and failover</H3>
      <DataTable
        columns={[
          { key: "var", header: "Setting", width: "w-[30%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "why", header: "Why" },
        ]}
        rows={[
          { id: "attempts", cells: { var: <code>retry_max_attempts</code>, value: "3", why: "Per provider, before failing over" } },
          { id: "base", cells: { var: <code>retry_base_delay</code>, value: "1.0 s", why: "Exponential backoff with jitter" } },
          {
            id: "max",
            cells: {
              var: <code>retry_max_delay</code>,
              value: "20.0 s",
              why: "Doubles as the quota-exhaustion signal: a Retry-After LARGER than this means the daily quota is spent, so the client fails over immediately instead of sleeping. The line is drawn here because this value is already defined as the longest we are ever willing to wait on one provider",
            },
            highlight: true,
          },
          { id: "timeout", cells: { var: <code>llm_timeout_seconds</code>, value: "60.0", why: "Per request" } },
        ]}
        caption="Free tiers signal two very different situations with the same 429. Retry-After: 2 is a burst limit and retrying the same provider is right; Retry-After: 3600 means that provider is dead for the window and no amount of waiting fixes it."
      />

      <H2 id="retrieval-knobs">Retrieval and ranking</H2>
      <DataTable
        columns={[
          { key: "var", header: "Setting", width: "w-[32%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "status", header: "Provenance", width: "w-[18%]" },
        ]}
        rows={[
          { id: "cand", cells: { var: <code>retrieval_candidates_per_leg</code>, value: "20", status: "design" } },
          { id: "fusion", cells: { var: <code>retrieval_fusion_top_k</code>, value: "20", status: "design" } },
          { id: "rin", cells: { var: <code>rerank_input_top_k</code>, value: "8", status: "measured" }, highlight: true },
          { id: "rtop", cells: { var: <code>rerank_top_k</code>, value: "5", status: "design" } },
          { id: "rrfk", cells: { var: <code>rrf_k</code>, value: "60", status: "literature" } },
          { id: "w", cells: { var: <code>rrf_weight_bm25 / _vector</code>, value: "1.0 / 1.0", status: "open question" }, highlight: true },
          { id: "ef", cells: { var: <code>hnsw_ef_search</code>, value: "100", status: "design" } },
          { id: "emb", cells: { var: <code>embedding_model_name</code>, value: "BAAI/bge-small-en-v1.5", status: "design" } },
          {
            id: "dim",
            cells: { var: <code>embedding_dim</code>, value: "384", status: "hard constraint" },
            note: "changing it needs a column migration, a reindex AND a full re-ingest",
          },
          { id: "rrenab", cells: { var: <code>RERANKER_ENABLED</code>, value: "true", status: "deployment lever" }, highlight: true },
          { id: "rrmodel", cells: { var: <code>reranker_model_name</code>, value: "BAAI/bge-reranker-base", status: "design" } },
          { id: "rrbatch", cells: { var: <code>reranker_batch_size</code>, value: "16", status: "design" } },
          { id: "rrlen", cells: { var: <code>reranker_max_length</code>, value: "512", status: "model limit" } },
          { id: "cond", cells: { var: <code>conditional_rerank_enabled</code>, value: "false", status: "deliberate" } },
          { id: "window", cells: { var: <code>rerank_ambiguity_window</code>, value: "5", status: "design" } },
          { id: "margin", cells: { var: <code>rerank_margin_threshold</code>, value: "0.10", status: "measured" } },
        ]}
      />

      <H2 id="generation-knobs">Generation and validation</H2>
      <DataTable
        columns={[
          { key: "var", header: "Setting", width: "w-[32%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "status", header: "Provenance", width: "w-[18%]" },
        ]}
        rows={[
          { id: "cr", cells: { var: <code>confidence_threshold_rerank</code>, value: "0.45", status: "guess" }, highlight: true },
          { id: "cf", cells: { var: <code>confidence_threshold_fused</code>, value: "0.015", status: "guess" }, highlight: true },
          { id: "temp", cells: { var: <code>llm_temperature</code>, value: "0.1", status: "design" } },
          { id: "maxtok", cells: { var: <code>llm_max_tokens</code>, value: "1024", status: "design" } },
          { id: "qre", cells: { var: <code>query_rewrite_enabled</code>, value: "true", status: "design" } },
          { id: "qrh", cells: { var: <code>query_rewrite_history_turns</code>, value: "6", status: "guess" } },
          { id: "qrm", cells: { var: <code>query_rewrite_max_tokens</code>, value: "120", status: "design" } },
          { id: "cve", cells: { var: <code>citation_validation_enabled</code>, value: "true", status: "design" } },
          { id: "cvt", cells: { var: <code>citation_similarity_threshold</code>, value: "0.50", status: "deliberate" } },
          {
            id: "abst",
            cells: { var: <code>abstention_message</code>, value: "fixed string", status: "contract" },
            note: "the prompt, the detector and the eval assertions must all agree on it",
          },
        ]}
      />

      <H2 id="cache-knobs">Caching</H2>
      <DataTable
        columns={[
          { key: "var", header: "Setting", width: "w-[32%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "why", header: "Why" },
        ]}
        rows={[
          {
            id: "en",
            cells: {
              var: <code>CACHE_ENABLED</code>,
              value: "true",
              why: "Turn off entirely on a Redis-free deployment. Every call is wrapped anyway, so a failure degrades to a miss",
            },
          },
          {
            id: "ttl",
            cells: {
              var: <code>cache_ttl_seconds</code>,
              value: "3600",
              why: "Shorter than the freshness requirement. It is a backstop for bugs in active invalidation, not the primary mechanism",
            },
          },
          { id: "sem", cells: { var: <code>semantic_cache_enabled</code>, value: "true", why: "The fuzzy path" } },
          {
            id: "semt",
            cells: {
              var: <code>semantic_cache_threshold</code>,
              value: "0.95",
              why: "Survivable only because identifier queries skip this path entirely and abstentions are never cached",
            },
            highlight: true,
          },
          {
            id: "semmax",
            cells: { var: <code>semantic_cache_max_candidates</code>, value: "200", why: "Bounds the similarity scan" },
          },
        ]}
      />

      <H2 id="provenance">What the provenance labels mean</H2>
      <DataTable
        columns={[
          { key: "label", header: "Label", width: "w-[22%]" },
          { key: "means", header: "Means" },
        ]}
        rows={[
          { id: "design", cells: { label: "design", means: "Comes from the system design, and has a stated rationale" } },
          { id: "lit", cells: { label: "literature", means: "From a published result, cited in the code comment" } },
          {
            id: "measured",
            cells: { label: "measured", means: "An experiment produced this number, and the experiment is reproducible" },
            highlight: true,
          },
          {
            id: "guess",
            cells: {
              label: "guess",
              means: "Provisional, and labelled so in the config file itself. These are the ones to distrust first",
            },
            highlight: true,
          },
          { id: "deliberate", cells: { label: "deliberate", means: "Chosen against the obvious value, for a reason recorded in an ADR" } },
          { id: "open", cells: { label: "open question", means: "Evidence exists that this is wrong, and the experiment has not been run" } },
        ]}
      />

      <Callout kind="caution" title="Why the labels are worth the column">
        <p>
          One threshold in this system sat in configuration with a confident comment explaining its
          reasoning, and was wrong by 4x in the direction that made its own feature invisible. It
          would have been caught years later, or never. The provenance column is the cheapest defence
          against that, and the honest labels — <em>guess</em>, <em>open question</em> — are the ones
          doing the work.
        </p>
      </Callout>

      <H2 id="virtual-cost">The virtual price table</H2>
      <p>
        Real spend is zero, so cost is modelled: for each model in use, the paid-tier price of the
        same model, or the closest comparable hosted model. A conservative mid-range fallback covers
        anything not in the table, so cost is never silently zero for an unknown model.
      </p>
      <CodeBlock
        language="python"
        filename="app/config.py"
        code={`VIRTUAL_PRICES = {                        # USD per 1M tokens · snapshot: July 2026
    "llama-3.1-8b-instant":      (0.05, 0.08),
    "llama-3.3-70b-versatile":   (0.59, 0.79),
    "qwen/qwen3-32b":            (0.29, 0.59),
    "gemini-2.5-flash":          (0.30, 2.50),
    "…:free":                    (0.59, 0.79),   # priced as the paid route
    "llama3.1:8b":               (0.05, 0.08),   # local — priced as a comparable hosted 8B
}
DEFAULT_VIRTUAL_PRICE = (0.50, 1.50)`}
      />
      <p>
        With paid APIs this table disappears — cost comes from the provider invoice and the tracking
        code stays identical.
      </p>

      <p>
        <Link href="/docs/decisions">The decision record →</Link>
      </p>
    </DocPage>
  );
}
