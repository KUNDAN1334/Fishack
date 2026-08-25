import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/operations")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function OperationsDocPage() {
  return (
    <DocPage
      href="/docs/operations"
      eyebrow="Operations"
      title="Running and operating"
      lead="The dashboard is organised around the four questions an operator actually arrives with, not around the metric families the API happens to return. This page says what each number means, which direction is bad, and what to do when it moves."
    >
      <H2 id="four-questions">The four questions</H2>
      <p>
        Every panel on <Link href="/admin">the operations dashboard</Link> answers one of these.
        Naming the sections after the decision rather than the metric is the whole reorganisation:
        &ldquo;Latency&rdquo; is a metric family, &ldquo;Is it fast?&rdquo; is what someone opened
        the page to find out.
      </p>

      <DataTable
        columns={[
          { key: "q", header: "Question", width: "w-[22%]" },
          { key: "shows", header: "What it shows" },
          { key: "bad", header: "Which direction is bad" },
        ]}
        rows={[
          {
            id: "working",
            cells: {
              q: "Is it working?",
              shows: "Request volume, escalation rate, cache hit rate, cost per query, and the outcome of every request",
              bad: "Escalation rate cuts BOTH ways — see below",
            },
          },
          {
            id: "fast",
            cells: {
              q: "Is it fast?",
              shows: "p50, p95, and mean latency per stage as bars",
              bad: "p95 above 3s. The bars say which stage owns it, and it is almost always the reranker",
            },
          },
          {
            id: "trust",
            cells: {
              q: "Is it trustworthy?",
              shows: "Satisfaction, fabricated-citation count, mean confidence, open escalations by reason",
              bad: "Any fabricated citation at all. Satisfaction is noisy at low volume",
            },
            highlight: true,
          },
          {
            id: "leak",
            cells: {
              q: "Is it leaking?",
              shows: "Per-tenant traffic, escalation rate, cache hits, p95 and cost",
              bad: "A row appearing that should not exist. The numbers themselves are just volume",
            },
          },
          {
            id: "cost",
            cells: {
              q: "What would it cost?",
              shows: "Virtual cost totals, token counts, and per-provider usage against free-tier quota",
              bad: "One provider carrying everything means the fallback chain is untested in practice",
            },
          },
        ]}
      />

      <H3 id="escalation-rate">Escalation rate is the one metric that cuts both ways</H3>
      <p>
        Too high means retrieval is failing, or the corpus has a real gap, or the threshold is
        miscalibrated. <strong>Too low means the confidence gate is protecting nobody</strong> — a
        system that never declines is a system that answers questions it cannot answer, which is the
        exact failure the whole design exists to prevent.
      </p>
      <p>
        So it is displayed with a good/warn/bad band rather than as &ldquo;lower is better&rdquo;,
        and the breakdown by reason is what makes it actionable.
      </p>

      <DataTable
        columns={[
          { key: "reason", header: "Escalation reason", width: "w-[26%]" },
          { key: "means", header: "What a spike means" },
          { key: "do", header: "What to do" },
        ]}
        rows={[
          {
            id: "low",
            cells: {
              reason: <code>low_confidence</code>,
              means: "Retrieval found something, and not strongly enough",
              do: "Run `make tune` against the golden set; check whether recent ingestion changed chunk boundaries",
            },
          },
          {
            id: "no-results",
            cells: {
              reason: <code>no_results</code>,
              means: "Nothing matched at all — usually genuinely out of scope",
              do: "Read the escalation queries. A cluster is a documentation gap, and it is the clearest signal you will ever get about what customers ask that you have not written down",
            },
            highlight: true,
          },
          {
            id: "model",
            cells: {
              reason: <code>model_abstained</code>,
              means: "Context was topically right and factually silent",
              do: "Also a corpus gap, and a more interesting one — retrieval found the right area and the answer was not there",
            },
          },
          {
            id: "gen",
            cells: {
              reason: <code>generation_failed</code>,
              means: "Every provider in the chain errored or was exhausted",
              do: "Check provider quota on the same page. A spike here beside a flat low_confidence count is an outage signal, not a quality signal",
            },
          },
        ]}
      />

      <Callout kind="note" title="Amber, not rose">
        <p>
          The escalation panel is amber throughout. An abstention is the gate doing its job, and a
          rising count means the corpus has a gap rather than that the system is broken. Colouring it
          as an error would train an operator to treat correct behaviour as a fault, and the first
          thing they would do about it is lower the threshold.
        </p>
      </Callout>

      <H2 id="reading-numbers">Reading the numbers honestly</H2>
      <DataTable
        columns={[
          { key: "metric", header: "Metric", width: "w-[24%]" },
          { key: "caveat", header: "What would make it misleading" },
        ]}
        rows={[
          {
            id: "sat",
            cells: {
              metric: "Satisfaction",
              caveat:
                "Computed over RATED answers only. At demo volume a single vote moves it several points — read the direction, not the decimal",
            },
          },
          {
            id: "conf",
            cells: {
              metric: "Mean confidence",
              caveat:
                "Averages two scales roughly 30x apart, because some requests were reranked and some were not. It is a trend, never an absolute — the per-answer pill in the assistant shows which scale each one is on",
            },
            highlight: true,
          },
          {
            id: "stages",
            cells: {
              metric: "Per-stage latency",
              caveat:
                "Means, not percentiles — per-stage percentiles are not recorded, so one slow request moves a bar in a way it would not move a p95. The shape is the finding",
            },
          },
          {
            id: "cache",
            cells: {
              metric: "Cache hit rate",
              caveat:
                "Includes semantic hits, which serve an answer written for a DIFFERENT question. A high rate is good; a high SEMANTIC rate deserves a look at what is matching",
            },
          },
          {
            id: "cost-metric",
            cells: {
              metric: "Cost per query",
              caveat:
                "Virtual. And a cache hit records zero — deliberately, because replaying the original spend would make cost rise as caching improved",
            },
          },
        ]}
      />

      <H2 id="health">Health and startup</H2>
      <p>
        <code>GET /health</code> reports each dependency independently, so a broken Redis does not
        mask a healthy Postgres or the other way round. It never raises — a health endpoint that
        can fail is one more thing to page about.
      </p>
      <CodeBlock
        language="json"
        code={`{
  "status": "ok",
  "database": { "ok": true, "pgvector_installed": true },
  "redis": { "ok": true },
  "llm_chain": ["groq", "gemini", "openrouter"]
}`}
      />
      <p>
        Startup loads both local models before the app accepts traffic, and{" "}
        <strong>fails the boot</strong> if the embedding model&apos;s dimension does not match the
        schema&apos;s <code>vector(384)</code>. A dimension mismatch that survives startup would
        surface as a per-query error under load, which is a far worse place to find out.
      </p>

      <H2 id="feedback">Feedback triage</H2>
      <p>
        Thumbs-down feedback is classified by heuristic rather than by a model, because every signal
        needed is already on the trace row: the confidence and its scale, the citation report,
        whether a cited chunk was contested, and the cache status. So classification is free,
        instant, deterministic and <em>explainable</em> — &ldquo;retrieval failure, because
        confidence was 0.31 against a 0.45 threshold&rdquo; is a sentence you can argue with.
      </p>

      <H3 id="check-order">The check order is the actual design</H3>
      <DataTable
        columns={[
          { key: "order", header: "Order", width: "w-[8%]", numeric: true },
          { key: "check", header: "Check" },
          { key: "why", header: "Why it comes here" },
        ]}
        rows={[
          {
            id: "1",
            cells: {
              order: "1",
              check: "Cache",
              why: "A hit means retrieval and generation never ran for this request. Blaming retrieval for an answer it did not produce sends someone to debug the wrong component entirely",
            },
            highlight: true,
          },
          {
            id: "2",
            cells: {
              order: "2",
              check: "Stale data",
              why: "The model may have followed the prompt perfectly while the context was out of date. That is an ingestion problem wearing a generation problem's clothes",
            },
          },
          {
            id: "3",
            cells: {
              order: "3",
              check: "Retrieval",
              why: "If the right chunks never arrived, no prompt could have produced a good answer",
            },
          },
          {
            id: "4",
            cells: {
              order: "4",
              check: "Generation",
              why: "What is left once the three above are ruled out",
            },
          },
        ]}
      />

      <p>
        <code>unclear</code> is a real category and is reported separately rather than forced into a
        neighbour. A misclassified failure is worse than an unclassified one — it points at the
        wrong component with confidence, and the real bug survives the investigation.
      </p>

      <Callout kind="caution" title="Thumbs-up produces golden-set candidates, not cases">
        <p>
          Users approve confident-sounding answers; satisfaction is not correctness. Auto-promoting
          production output into ground truth would let the system grade itself, which is the
          correlated-failure problem in different clothing. The promotion script also rejects any
          answer with fabricated citations or a grounding rate below 0.8, and leaves the expected
          sources empty for a human to fill in.
        </p>
      </Callout>

      <H2 id="runbook">Runbook</H2>
      <DataTable
        columns={[
          { key: "symptom", header: "Symptom", width: "w-[28%]" },
          { key: "likely", header: "Most likely cause" },
          { key: "action", header: "First action" },
        ]}
        rows={[
          {
            id: "s1",
            cells: {
              symptom: "Escalation rate jumps, low_confidence dominates",
              likely: "A re-ingest changed chunk boundaries, or the threshold drifted from the corpus",
              action: "Run `make eval-retrieval` and compare against the committed baseline",
            },
          },
          {
            id: "s2",
            cells: {
              symptom: "generation_failed spikes",
              likely: "Every provider exhausted, or a model name was retired",
              action: "Check provider usage on the dashboard, then /health. A 404 from a provider is a config problem",
            },
            highlight: true,
          },
          {
            id: "s3",
            cells: {
              symptom: "Cache hit rate falls to zero",
              likely: "Redis is unreachable, or its free-tier command quota is spent",
              action: "Nothing breaks — every call degrades to a miss. Confirm on /health, then decide whether to disable the cache explicitly",
            },
          },
          {
            id: "s4",
            cells: {
              symptom: "p95 above 3s",
              likely: "The cross-encoder",
              action: "Set RERANKER_ENABLED=false. Measurements say vector-only has the better recall@5 on this corpus anyway",
            },
          },
          {
            id: "s5",
            cells: {
              symptom: "A fabricated citation appears",
              likely: "The model invented a marker index",
              action: "Read the trace. This is already surfaced in the answer and counted on the dashboard — it should be zero, and any non-zero value is worth a look",
            },
          },
          {
            id: "s6",
            cells: {
              symptom: "degraded_legs on many answers",
              likely: "One retrieval leg is erroring",
              action: "Answers are still being built, on less evidence. Check Postgres and the GIN/HNSW indexes",
            },
          },
          {
            id: "s7",
            cells: {
              symptom: "A tenant appears in the per-tenant table that should not exist",
              likely: "This is the leak signal",
              action: "Stop and investigate. The isolation tripwire should have raised before this — if it did not, a code path is bypassing the scope",
            },
          },
        ]}
      />

      <H2 id="admin-auth">Protecting the dashboard</H2>
      <Callout kind="caution" title="This is the one endpoint that reads across tenants">
        <p>
          Request volume, cost and query counts for every tenant. Publicly exposed, that is a data
          leak. With <code>ADMIN_TOKEN</code> unset the endpoint is <strong>open</strong>, which is
          right locally and wrong anywhere else.
        </p>
      </Callout>
      <p>Pick one before deploying:</p>
      <ul>
        <li>
          <strong>Set an admin token.</strong> The frontend&apos;s route handler attaches it
          server-side, so it never reaches the browser bundle. Same value on both sides.
        </li>
        <li>
          <strong>Block it at the edge.</strong> Remove the rewrite for <code>/api/admin/*</code> and
          it is unreachable through the frontend.
        </li>
        <li>
          <strong>Do not deploy the dashboard</strong> and read statistics through a tunnel.
        </li>
      </ul>
      <p>
        In production this belongs behind SSO with an admin role, with every access audited. A
        shared token is the floor, not the target.
      </p>

      <p>
        <Link href="/docs/deployment">Deployment, where memory is the whole problem →</Link>
      </p>
    </DocPage>
  );
}
