import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/api")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/** One row per endpoint, rendered as a labelled method + path. */
function Endpoint({
  method,
  path,
  summary,
}: {
  method: "GET" | "POST";
  path: string;
  summary: string;
}) {
  return (
    <div className="!mt-6 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-2">
      <span
        className={`figure rounded-sm px-1.5 py-0.5 text-2xs font-semibold ${
          method === "GET" ? "bg-ocean-50 text-ocean-700" : "bg-emerald-50 text-emerald-700"
        }`}
      >
        {method}
      </span>
      <code className="!border-0 !bg-transparent !px-0 text-[15px] font-semibold text-slate-900">
        {path}
      </code>
      <span className="w-full text-sm text-slate-500 sm:w-auto">{summary}</span>
    </div>
  );
}

export default function ApiPage() {
  return (
    <DocPage
      href="/docs/api"
      eyebrow="Operations"
      title="API reference"
      lead="Five endpoints. The interesting one streams server-sent events in a fixed order that the interface depends on, and the second most interesting one exists only because streaming is miserable to test with a plain HTTP client."
    >
      <Callout kind="note" title="Everything is same-origin from the browser">
        <p>
          The frontend calls relative <code>/api/…</code> paths, which the Next server rewrites onto
          FastAPI. The paths below are the <em>backend&apos;s</em> paths; from the browser they carry
          an <code>/api</code> prefix.
        </p>
      </Callout>

      <H2 id="chat">Chat</H2>

      <Endpoint method="POST" path="/chat" summary="Answer a question, streaming." />

      <H3 id="chat-request">Request</H3>
      <CodeBlock
        language="json"
        code={`{
  "tenant_id": "acme",
  "query": "What is the webhook retry limit?",
  "messages": [
    { "role": "user", "content": "…" },
    { "role": "assistant", "content": "…" }
  ],
  "conversation_id": "b6f1…"      // client-generated UUID, or null
}`}
      />

      <DataTable
        columns={[
          { key: "field", header: "Field", width: "w-[22%]" },
          { key: "type", header: "Type", width: "w-[16%]" },
          { key: "notes", header: "Notes" },
        ]}
        rows={[
          {
            id: "tenant",
            cells: {
              field: <code>tenant_id</code>,
              type: "string",
              notes:
                "Validated against the tenants table, so a typo returns 404 rather than an empty result set that reads as 'we have no documentation about that'",
            },
          },
          {
            id: "query",
            cells: { field: <code>query</code>, type: "string", notes: "Empty or whitespace-only returns 422" },
          },
          {
            id: "messages",
            cells: {
              field: <code>messages</code>,
              type: "array",
              notes:
                "Prior turns, text only. The server is stateless — history is an INPUT to query rewriting, not server state, which is why any replica can serve any request",
            },
            highlight: true,
          },
          {
            id: "conv",
            cells: {
              field: <code>conversation_id</code>,
              type: "string | null",
              notes:
                "Persisted on the trace row so multi-turn traces group together in observability, feedback triage and the golden set. Not used for state",
            },
          },
        ]}
      />

      <Callout kind="caution" title="tenant_id in the body is a demonstration affordance">
        <p>
          In a real deployment it comes from the authenticated session or a JWT claim and is never
          accepted from the client — a client-supplied tenant id is a trivial cross-tenant read. The
          scope would be constructed from the auth context instead, and nothing below it in the
          pipeline changes.
        </p>
      </Callout>

      <H3 id="chat-events">Response — server-sent events, in this order</H3>
      <CodeBlock
        language="text"
        code={`event: meta
data: {"data":{"citations":[…],"gate":{…},"rewrite":{…},"cache_status":"miss"}}

event: delta
data: {"text":"The webhook retry limit is "}

event: delta
data: {"text":"5 attempts [2]. "}

event: final
data: {"data":{ … the complete ChatResponse … }}`}
      />

      <p>
        <code>meta</code> arriving before the first <code>delta</code> is a{" "}
        <strong>contract</strong>, not an implementation detail: it is what lets the sources panel
        populate while the answer is still being written. An <code>error</code> event only ever
        appears after the stream has begun — before that, errors are ordinary HTTP, because once the
        status line has been sent a 500 is no longer available.
      </p>

      <H3 id="chat-response">The final payload</H3>
      <DataTable
        columns={[
          { key: "field", header: "Field", width: "w-[26%]" },
          { key: "type", header: "Type", width: "w-[18%]" },
          { key: "notes", header: "Notes" },
        ]}
        rows={[
          { id: "answer", cells: { field: <code>answer</code>, type: "string", notes: "The full text, with inline [n] markers" } },
          {
            id: "action",
            cells: {
              field: <code>action</code>,
              type: '"answered" | "abstained" | "escalated" | "cache_hit"',
              notes: "All three abstention paths set 'escalated', so the escalation rate cannot understate reality",
            },
            highlight: true,
          },
          {
            id: "citations",
            cells: {
              field: <code>citations[]</code>,
              type: "Citation[]",
              notes:
                "index, chunk_id, title, source_type, source_path, heading_path, doc_version, effective_date, score, is_contested, was_cited",
            },
          },
          {
            id: "report",
            cells: {
              field: <code>citation_report</code>,
              type: "CitationReport | null",
              notes: "claims[] with per-claim supported/similarity, invalid_indices (fabrications), unused_indices",
            },
          },
          {
            id: "gate",
            cells: {
              field: <code>gate</code>,
              type: "GateDecision | null",
              notes:
                "should_generate, reason, top_score, threshold, and score_kind — the last is required to interpret the first two, because the scales differ ~30x",
            },
            highlight: true,
          },
          {
            id: "rewrite",
            cells: {
              field: <code>rewrite</code>,
              type: "RewriteResult | null",
              notes: "original, rewritten, changed, skipped_reason, elapsed_ms",
            },
          },
          {
            id: "cache",
            cells: {
              field: <code>cache_status</code>,
              type: '"miss" | "exact_hit" | "semantic_hit"',
              notes: "With cache_similarity on a semantic hit — the reader is looking at an answer written for a different question",
            },
          },
          {
            id: "cost",
            cells: {
              field: <code>virtual_cost_usd</code>,
              type: "number",
              notes: "Zero on a cache hit, deliberately. Replaying the original spend would make cost rise as caching improved",
            },
          },
          {
            id: "timings",
            cells: {
              field: <code>*_ms</code>,
              type: "number",
              notes: "rewrite, retrieval, rerank, generation, validation, total. Zero means the stage did not run",
            },
          },
          {
            id: "degraded",
            cells: {
              field: <code>degraded_legs[]</code>,
              type: "string[]",
              notes: "A retrieval leg that failed. The answer was built on less evidence than usual",
            },
          },
        ]}
      />

      <Endpoint
        method="POST"
        path="/chat/sync"
        summary="The same pipeline, one JSON object, no streaming."
      />
      <p>
        It exists because streaming is miserable to test with a plain HTTP client and because the
        evaluation harness wants a single object. It runs the <em>identical</em> pipeline — the
        synchronous entry point simply drains the stream — so it can never diverge from what users
        actually get.
      </p>

      <H2 id="feedback">Feedback</H2>
      <Endpoint method="POST" path="/feedback" summary="Record a thumbs rating against a trace." />
      <CodeBlock
        language="json"
        code={`{ "trace_id": "…", "rating": 1, "comment": null }   // rating: 1 | -1`}
      />
      <p>
        Fire-and-forget from the client&apos;s point of view: the button lights optimistically, and a
        failed POST is not worth interrupting someone&apos;s reading over. The feedback flywheel
        loses one data point and nothing else breaks.
      </p>

      <H2 id="admin">Admin</H2>
      <Endpoint
        method="GET"
        path="/admin/stats?hours=&tenant_id="
        summary="Aggregates from the traces table. Reads across tenants."
      />
      <p>
        Guarded by an admin-token dependency on the router. Every figure is computed by the backend
        from the traces table; the frontend does no arithmetic beyond formatting, deliberately — if
        the dashboard derived its own rates they could disagree with what the eval harness and the
        triage script read from the same rows.
      </p>
      <CodeBlock
        language="json"
        code={`{
  "window":   { "hours": 24, "since": "…", "tenant_id": null },
  "requests": { "total": 0, "escalation_rate": 0, "cache_hit_rate": 0, "by_action": {} },
  "latency_ms": { "p50": 0, "p95": 0, "mean_retrieval": 0, "mean_rerank": 0, "mean_generation": 0 },
  "cost":     { "methodology": "…", "total_usd": 0, "per_query_usd": 0, "tokens_in": 0, "tokens_out": 0 },
  "quality":  { "thumbs_up": 0, "thumbs_down": 0, "satisfaction_rate": 0,
                "answers_with_fabricated_citations": 0, "mean_confidence": 0 },
  "escalations": { "open": 0, "by_reason": {} },
  "by_tenant":   [ { "tenant_id": "acme", "requests": 0, … } ],
  "providers":   { "groq": { "requests": 0, "tokens_in": 0, "virtual_cost_usd": 0 } }
}`}
      />

      <Endpoint method="POST" path="/admin/cache/flush?tenant_id=" summary="Drop one tenant's cached answers." />

      <H2 id="health">Health</H2>
      <Endpoint method="GET" path="/health" summary="Liveness plus an independent report per dependency." />
      <p>
        Each dependency reports separately so a broken Redis does not mask a healthy Postgres. The
        endpoint reports rather than raises — a health check that can fail is one more thing to page
        about.
      </p>

      <H2 id="errors">Error taxonomy</H2>
      <DataTable
        columns={[
          { key: "status", header: "Status", numeric: true, width: "w-[14%]" },
          { key: "when", header: "When" },
          { key: "shape", header: "Shape" },
        ]}
        rows={[
          { id: "422", cells: { status: "422", when: "Empty query", shape: "FastAPI validation detail" } },
          {
            id: "404",
            cells: {
              status: "404",
              when: "Unknown tenant",
              shape: "detail: unknown tenant 'x' — deliberately not an empty result set",
            },
            highlight: true,
          },
          { id: "401", cells: { status: "401", when: "Admin token missing or wrong", shape: "The dashboard says which side to fix" } },
          {
            id: "502",
            cells: {
              status: "502",
              when: "The frontend route handler cannot reach the API",
              shape: "detail naming the origin it tried",
            },
          },
          {
            id: "sse",
            cells: {
              status: "200 + error event",
              when: "The pipeline raises after the stream has begun",
              shape:
                "A terminal SSE error event. The client gets a definite end state rather than a connection that just stops, which is indistinguishable from a network failure",
            },
            highlight: true,
          },
        ]}
      />

      <p>
        <Link href="/docs/configuration">Every environment variable and tuning knob →</Link>
      </p>
    </DocPage>
  );
}
