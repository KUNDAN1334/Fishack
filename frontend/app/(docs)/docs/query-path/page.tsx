import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Steps from "@/components/docs/Steps";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/query-path")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function QueryPathPage() {
  return (
    <DocPage
      href="/docs/query-path"
      eyebrow="Architecture"
      title="The query path"
      lead="One readable sequence in app/generation/pipeline.py. Each stage may decline to hand work to the next, and every way of declining routes through a single exit — because an escalation row, a trace's action and the sentence the user reads must never be able to disagree."
    >
      <H2 id="stages">Eight stages</H2>
      <Steps
        steps={[
          {
            title: "Resolve the tenant, once",
            aside: "TenantScope",
            body: (
              <>
                A scope is constructed at the top of the request and threaded through everything
                below it. Functions take a <code>TenantScope</code>, never a{" "}
                <code>tenant_id: str</code> — so there is no signature in the retrieval layer that
                would even accept an unscoped read.
              </>
            ),
          },
          {
            title: "Rewrite a follow-up into a standalone question",
            aside: "skipped on turn 1",
            body: (
              <>
                Skipped entirely when there is no history: a question with no conversation behind it
                is standalone by definition, and rewriting could only paraphrase it at the cost of a
                round trip and a chance to mangle an error code. Otherwise the last six turns go in
                at temperature 0.0, and the <em>output is validated before it is used</em>.
              </>
            ),
          },
          {
            title: "Probe the cache — exact first, then semantic",
            aside: "after the rewrite",
            body: (
              <>
                Exact is an O(1) lookup that cannot be wrong. Semantic needs an embedding and a scan
                and <em>can</em> be wrong, so the cheap safe one goes first. Identifier-bearing
                queries skip the semantic path entirely, on read and on write.
              </>
            ),
          },
          {
            title: "Retrieve",
            aside: "~29 ms p50",
            body: (
              <>
                The keyword and vector legs run concurrently against different indexes on separate
                pooled connections, so hybrid retrieval costs roughly max(legs) rather than their
                sum. Their ranked lists are merged by reciprocal rank fusion into twenty candidates.
              </>
            ),
          },
          {
            title: "Rerank the top eight",
            aside: "1.7–3.3 s on CPU",
            body: (
              <>
                A local cross-encoder scores query–chunk pairs and emits the top five. Only eight
                candidates reach it: cost is linear in pairs, and narrowing the second stage rather
                than the first means recall@20 still measures the same twenty chunks.
              </>
            ),
          },
          {
            title: "Gate on confidence, before generation",
            aside: "two thresholds",
            body: (
              <>
                Below the threshold, the pipeline abstains and opens an escalation without calling
                the model at all. Which threshold applies is read from the <em>data</em> — whether
                a reranker score is present — not from configuration, because configuration knows
                the intent and only the result knows what happened.
              </>
            ),
          },
          {
            title: "Generate, closed-book, streamed",
            aside: "temperature 0.1",
            body: (
              <>
                The model sees the retrieved chunks and nothing else, with a few-shot prompt that
                requires an inline citation per claim and instructs it to prefer the newest source
                and flag a discrepancy when sources conflict. Not temperature 0.0 — open models
                repeat themselves there.
              </>
            ),
          },
          {
            title: "Validate the citations, then record",
            aside: "~30 ms",
            body: (
              <>
                The answer is split into sentence-level claims and each is checked against the chunk
                it cited, in one batched embedding call. Then the trace row is written and the
                answer is cached — unless it was an abstention, which is never cached.
              </>
            ),
          },
        ]}
      />

      <H2 id="event-contract">The streaming contract</H2>
      <p>
        Three server-sent event types arrive in a fixed order, and the ordering is a designed
        feature rather than an implementation detail.
      </p>

      <DataTable
        columns={[
          { key: "event", header: "Event", width: "w-[16%]" },
          { key: "when", header: "When" },
          { key: "payload", header: "Payload" },
        ]}
        rows={[
          {
            id: "meta",
            cells: {
              event: <code>meta</code>,
              when: "Before the first token of the answer",
              payload: "Numbered citations, the gate decision, the rewrite result, cache status",
            },
            highlight: true,
          },
          {
            id: "delta",
            cells: {
              event: <code>delta</code>,
              when: "Repeatedly, as the model produces text",
              payload: "One fragment of the answer",
            },
          },
          {
            id: "final",
            cells: {
              event: <code>final</code>,
              when: "Once, last",
              payload: "The complete response: timings, cost, provider, trace id, citation report",
            },
          },
          {
            id: "error",
            cells: {
              event: <code>error</code>,
              when: "Only after the stream has already begun",
              payload: "A terminal message — the HTTP status is long gone by then",
            },
          },
        ]}
      />

      <Callout kind="note" title="Why meta comes first">
        <p>
          Because the sources panel must populate <em>while the answer is still typing</em>. Someone
          watches the answer being assembled out of documents they can already see, which is the
          difference between asserting that answers are grounded and demonstrating it. Waiting for{" "}
          <code>final</code> and rendering everything at once would be simpler and would delete the
          most interesting thing the interface does.
        </p>
        <p>
          <code>final</code> is last for a duller reason: the citation report cannot exist until the
          answer does.
        </p>
      </Callout>

      <H3 id="sse-parsing">The client parses SSE by hand, and must</H3>
      <p>
        The browser has a built-in SSE client, <code>EventSource</code>, and it is GET-only. A chat
        request carries a tenant, a query and the conversation history — far too much for a query
        string, and putting a conversation in a URL is a bad idea regardless, because it lands in
        logs, in history and in referrers.
      </p>
      <p>
        So the frontend uses <code>fetch</code> with a POST body and reads the response stream. The
        rule that makes it correct: <strong>a network chunk is not an event</strong>. One read can
        deliver half an event, three events, or an event split mid-JSON, so bytes accumulate into a
        buffer and only complete <code>\n\n</code>-separated blocks are parsed, with the remainder
        kept for the next read. The decoder is called with <code>{`{ stream: true }`}</code> for the
        same reason: a multi-byte character split across two chunks would otherwise decode as a
        replacement character mid-word.
      </p>

      <Callout kind="caution" title="This is the classic streaming bug">
        <p>
          Parsing each network chunk independently works perfectly in development — where responses
          are small and arrive whole — and corrupts randomly in production under real network
          conditions. It is the kind of failure that reproduces once a day and never on your
          machine.
        </p>
      </Callout>

      <H2 id="exits">Every way out</H2>
      <p>
        There are seven, and six of them are not the happy path. Enumerating them is worth more than
        describing the successful one, because the whole product thesis is about what happens when
        the system cannot answer.
      </p>

      <CodeBlock
        language="text"
        filename="app/generation/pipeline.py — exit paths"
        code={`                       ┌─ cache hit           -> _serve_cached()  action = "cache_hit"
                       │
POST /chat -> stream() ┼─ every leg failed     -> _abstain(no_results)
                       │
                       ├─ gate: no results     -> _abstain(no_results)
                       ├─ gate: below threshold-> _abstain(low_confidence)
                       │
                       ├─ generation failed    -> _abstain(generation_failed)
                       │                          (+ an "error" event if text had already gone out)
                       │
                       ├─ the MODEL abstained  -> escalation, action = "escalated"
                       │
                       └─ success              -> validate -> cache -> action = "answered"`}
      />

      <H3 id="one-exit">Three abstention paths, one exit</H3>
      <p>
        The gate abstains on weak retrieval. The <em>model</em> abstains when the context was
        topically right and factually silent. Generation failure abstains when every provider died.
        All three route through one <code>_abstain()</code> function, all three write an escalation
        row, and all three set <code>action = &quot;escalated&quot;</code> on the trace.
      </p>
      <p>
        The reason is metric integrity. Three code paths setting the escalation row, the trace
        action and the user-facing sentence independently is exactly how an escalation-rate metric
        ends up lying about the system it measures. And an abstention is streamed as{" "}
        <code>meta</code> then <code>delta</code> like any other answer, not as an error shape —
        otherwise every consumer would need two branches for one legitimate outcome.
      </p>

      <DataTable
        columns={[
          { key: "path", header: "Abstention path", width: "w-[26%]" },
          { key: "means", header: "What it actually means" },
          { key: "fix", header: "Where the fix lives" },
        ]}
        rows={[
          {
            id: "gate",
            cells: {
              path: "Gate, below threshold",
              means: "Retrieval found something, and not strongly enough to answer from",
              fix: "Retrieval, chunking, or the threshold itself",
            },
          },
          {
            id: "none",
            cells: {
              path: "Gate, no results",
              means: "Nothing matched at all — usually genuinely out of scope",
              fix: "The corpus, if the question keeps recurring",
            },
          },
          {
            id: "model",
            cells: {
              path: "Model declined",
              means: "The context was on-topic and did not contain the answer",
              fix: "The corpus. This is the most interesting signal of the three — it is a documentation gap, not a retrieval bug",
            },
            highlight: true,
          },
          {
            id: "gen",
            cells: {
              path: "Generation failed",
              means: "Every provider in the chain errored or was exhausted",
              fix: "Provider configuration or quota. A spike here beside a flat low-confidence count is a much clearer outage signal than a raw 500 count",
            },
          },
        ]}
      />

      <Callout kind="note" title="Every abstention writes a row, including the obviously out-of-scope ones">
        <p>
          Those are not noise. A cluster of them is the single clearest signal of what customers ask
          about that you have not documented, and it is invisible if you only record the near-misses.
          The escalation carries the conversation and the top <strong>ten</strong> retrieved chunks
          with their scores — ten rather than five, because &ldquo;the right chunk was at rank
          7&rdquo; and &ldquo;the right chunk was never retrieved&rdquo; are different bugs.
        </p>
      </Callout>

      <H2 id="failure-handling">What happens when each dependency fails</H2>
      <DataTable
        columns={[
          { key: "fails", header: "When this fails", width: "w-[26%]" },
          { key: "behaviour", header: "Behaviour" },
          { key: "visible", header: "Where you see it" },
        ]}
        rows={[
          {
            id: "one-leg",
            cells: {
              fails: "One retrieval leg",
              behaviour: "The other leg's results are used alone; the request continues",
              visible: "degraded_legs on the answer's timing strip",
            },
          },
          {
            id: "both-legs",
            cells: {
              fails: "Both retrieval legs",
              behaviour: "Abstain with no_results, and open an escalation",
              visible: "Escalation banner, and the reason on the dashboard",
            },
          },
          {
            id: "redis",
            cells: {
              fails: "Redis",
              behaviour: "Every cache call is wrapped, so a failure degrades to a miss",
              visible: "Cache hit rate falling to zero",
            },
          },
          {
            id: "rewrite",
            cells: {
              fails: "Query rewriting",
              behaviour: "Fall back to the raw query and record why. A degraded rewrite gives worse retrieval; a raised exception gives no answer at all",
              visible: "skipped_reason on the rewrite result",
            },
          },
          {
            id: "provider",
            cells: {
              fails: "One LLM provider",
              behaviour: "Fail over to the next in the chain. A Retry-After larger than the maximum wait is read as quota exhaustion and fails over immediately rather than sleeping",
              visible: "Provider usage on the dashboard",
            },
          },
          {
            id: "all-providers",
            cells: {
              fails: "Every LLM provider",
              behaviour: "Abstain with generation_failed",
              visible: "A spike in that escalation reason",
            },
          },
          {
            id: "validation",
            cells: {
              fails: "Citation validation",
              behaviour: "The answer is still returned, with no report rather than no answer",
              visible: "An empty citation report",
            },
          },
          {
            id: "trace",
            cells: {
              fails: "Writing the trace",
              behaviour: "Swallowed. Observability failure must never become a user-facing one",
              visible: "Server logs only",
            },
          },
        ]}
      />

      <p>
        <Link href="/docs/retrieval">Retrieval and ranking, in detail →</Link>
      </p>
    </DocPage>
  );
}
