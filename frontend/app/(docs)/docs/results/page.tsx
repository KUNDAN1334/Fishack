import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import StatGrid from "@/components/docs/StatGrid";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/results")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/**
 * Every measured number this project claims, in one place.
 *
 * The organising rule: no figure appears without the command that reproduces it
 * and the condition that bounds it. That is not modesty — an unsourced number is
 * the exact failure this project's own field notes are about, where a threshold
 * that looked tuned had never been measured and was wrong by 4x.
 */

export default function ResultsPage() {
  return (
    <DocPage
      href="/docs/results"
      eyebrow="Evaluation"
      title="Measured results"
      lead="Every number this project claims, the command that reproduces it, and the caveat that bounds it. Two of these contradict the design document that specified the system, which is the most useful thing the harness produced."
    >
      <StatGrid
        columns={4}
        stats={[
          {
            label: "Golden set",
            value: "65",
            note: "cases across six types and two tenants",
          },
          {
            label: "Corpus",
            value: "312",
            note: "current chunks, 156 per tenant",
          },
          {
            label: "Retrieval p50",
            value: "29 ms",
            note: "retrieval only, before any reranking",
          },
          {
            label: "Test suite",
            value: "369 + 23",
            note: "unit plus integration",
          },
        ]}
      />

      <H2 id="retrieval">Retrieval strategies</H2>
      <p>
        Five arms over the same 65 cases and the same corpus. Retrieval only, so there are no LLM
        calls and the run is fully reproducible on any machine with the repository checked out.
      </p>

      <DataTable
        columns={[
          { key: "arm", header: "Arm", width: "w-[30%]" },
          { key: "r5", header: "recall@5", numeric: true },
          { key: "r20", header: "recall@20", numeric: true },
          { key: "mrr", header: "MRR", numeric: true },
          { key: "lat", header: "mean latency", numeric: true },
        ]}
        rows={[
          { id: "bm25", cells: { arm: "BM25 only", r5: "0.747", r20: "0.928", mrr: "0.677", lat: "10 ms" } },
          {
            id: "vector",
            cells: { arm: "Vector only", r5: "0.938", r20: "1.000", mrr: "0.820", lat: "40 ms" },
            note: "best recall@5 of any arm",
            highlight: true,
          },
          { id: "rrf", cells: { arm: "BM25 + vector (RRF)", r5: "0.910", r20: "0.982", mrr: "0.768", lat: "50 ms" } },
          {
            id: "rrf-rr",
            cells: { arm: "BM25 + vector + reranker", r5: "0.895", r20: "0.982", mrr: "0.863", lat: "1,700 ms" },
          },
          {
            id: "vec-rr",
            cells: { arm: "Vector + reranker", r5: "0.915", r20: "1.000", mrr: "0.893", lat: "3,300 ms" },
            note: "best MRR of any arm",
            highlight: true,
          },
        ]}
        caption="make eval-retrieval · macro-averaged over cases · both tenants."
      />

      <Callout kind="result" title="Hybrid retrieval did not beat vector-only on this corpus">
        <p>
          This contradicts the design document that specified hybrid retrieval, and it is the most
          useful thing the harness produced. A system that can only confirm its own design is not
          being measured.
        </p>
      </Callout>

      <H3 id="per-type">Where the average is hiding the finding</H3>
      <p>
        The overall number conceals two opposite effects that happen to cancel. Broken out by case
        type, MRR:
      </p>

      <DataTable
        columns={[
          { key: "type", header: "Question type", width: "w-[36%]" },
          { key: "bm25", header: "BM25", numeric: true },
          { key: "vector", header: "vector", numeric: true },
          { key: "hybrid", header: "hybrid", numeric: true },
        ]}
        rows={[
          {
            id: "ident",
            cells: { type: "Exact identifiers (ERR_TIMEOUT_502)", bm25: "0.542", vector: "0.652", hybrid: "0.726" },
            note: "the keyword leg earns its place here, exactly as designed",
            highlight: true,
          },
          {
            id: "multi",
            cells: { type: "Multi-turn follow-ups", bm25: "0.159", vector: "0.625", hybrid: "0.306" },
            note: "and destroys the result here",
            highlight: true,
          },
        ]}
      />

      <p>
        The keyword leg helps exactly where the design predicted and is near-useless on short,
        pronoun-heavy follow-ups. Equal-weight fusion then lets the harm win the average. Weighting
        the vector leg at 1.0 and the keyword leg at 0.5 is the obvious next experiment;{" "}
        <strong>it has not been run</strong>, and it is recorded as open rather than assumed.
      </p>

      <H3 id="sharpest">The sharpest single case</H3>
      <p>
        On <em>&ldquo;how long until my events show up in the dashboard?&rdquo;</em> the correct
        chunk sat at <strong>rank 7</strong> under vector search and <strong>rank 20</strong> after
        fusion. Only the top eight candidates reach the reranker, so blending pushed the right
        answer out of the reranker&apos;s reach entirely. The vector arm recovered it; the hybrid
        arm could not.
      </p>
      <p>
        That is a concrete mechanism rather than a statistical wobble, and it is the kind of finding
        that only exists because the harness reports per-case detail rather than a headline number.
      </p>

      <Callout kind="caveat" title="What bounds this result">
        <p>
          The corpus is AI-written prose: smooth, semantically coherent, and easy for an embedding
          model. Real documentation full of internal jargon, codenames and inconsistent phrasing
          would favour the keyword leg considerably more. This is a result about <em>this
          corpus</em>, not a result about retrieval in general — and the case counts per question
          type are small enough that a single case moves the average.
        </p>
      </Callout>

      <H2 id="chunking">Chunking: per-source versus fixed windows</H2>
      <p>
        The same corpus ingested twice — once with the three per-source chunkers, once with fixed
        1,600-character windows — under shadow tenants and scored identically.
      </p>

      <DataTable
        columns={[
          { key: "type", header: "Question type", width: "w-[26%]" },
          { key: "metric", header: "Metric" },
          { key: "naive", header: "naive", numeric: true },
          { key: "smart", header: "per-source", numeric: true },
        ]}
        rows={[
          { id: "o1", cells: { type: "Overall", metric: "recall@5", naive: "0.591", smart: "0.858" }, highlight: true },
          { id: "o2", cells: { type: "", metric: "recall@20", naive: "0.863", smart: "0.972" } },
          { id: "i1", cells: { type: "Exact identifiers", metric: "recall@5", naive: "0.667", smart: "1.000" } },
          { id: "i2", cells: { type: "", metric: "MRR", naive: "0.450", smart: "0.726" } },
          {
            id: "m1",
            cells: { type: "Multi-turn", metric: "recall@20", naive: "0.550", smart: "1.000" },
            highlight: true,
          },
        ]}
        caption="make chunking-experiment · shadow tenants, so both arms are scored by the same golden set through source locators."
      />

      <p>
        Naive chunking loses <strong>45% of multi-turn answers entirely</strong> — not ranked lower,
        absent from the top twenty. It cuts a ticket&apos;s question away from its resolution and
        strips the heading context that tells a chunk what it is about. This is the largest single
        effect measured anywhere in the project, and it is on the ingestion side rather than the
        retrieval side.
      </p>

      <Callout kind="caveat" title="A measurement artefact that cuts both ways">
        <p>
          Naive chunks carry no heading path, so a docs locator resolves to an entire page in that
          arm versus one section in the per-source arm. A larger expected set{" "}
          <em>depresses</em> recall and <em>inflates</em> precision and MRR for the naive arm. So
          the recall gap is somewhat overstated and the MRR gap understated.
        </p>
        <p>
          <code>hit@5</code> is immune to this and is now the experiment&apos;s headline metric.
          Stated in the experiment&apos;s own output as well as here — it is better to understate a
          result than to have to explain away an overstated one.
        </p>
      </Callout>

      <H2 id="latency">Latency and cost</H2>
      <DataTable
        columns={[
          { key: "stage", header: "", width: "w-[24%]" },
          { key: "retrieval", header: "retrieval only", numeric: true },
          { key: "rerank", header: "+ reranker", numeric: true },
          { key: "full", header: "full answer", numeric: true },
        ]}
        rows={[
          { id: "p50", cells: { stage: <strong>p50</strong>, retrieval: "29 ms", rerank: "1,548 ms", full: "measured per run" } },
          {
            id: "p95",
            cells: { stage: <strong>p95</strong>, retrieval: "71 ms", rerank: "5,290 ms", full: "measured per run" },
            highlight: true,
          },
        ]}
        caption="12-thread CPU, no GPU. Full-answer latency depends on which provider served the request, so it is reported live on the operations dashboard rather than fixed here."
      />

      <Callout kind="result" title="The cross-encoder costs more than the entire latency budget">
        <p>
          Mean 1.7–3.3 seconds, against a target of P95 under three seconds <em>for the whole
          request</em>. Buying +0.073 MRR for +3.3 seconds is a real product decision, and the
          numbers to make it are now on the table rather than in a hunch.
        </p>
        <p>
          On a GPU or a hosted reranker that is roughly 200 ms and an obvious yes. On this hardware
          it ships behind a flag — and being able to point at the measurement that justifies the
          deployment choice is a stronger artefact than deploying the heavier configuration would
          have been.
        </p>
      </Callout>

      <H3 id="cost">Cost is virtual, and says so everywhere</H3>
      <p>
        Real spend is <strong>$0.00</strong> — every provider is on a free tier. So cost is tracked
        as what the same token usage <em>would</em> cost at paid-API list prices, priced per token
        from the model that actually served each request, against a price table snapshotted from
        public price pages.
      </p>
      <p>
        The methodology label stays attached to every figure on the dashboard. Detached from it,
        &ldquo;cost per query&rdquo; reads as a bill. The figure exists to make the cost of a design
        choice visible <em>before</em> it is one.
      </p>

      <H2 id="what-harness-caught">What the harness caught that testing did not</H2>
      <p>
        This list is the harness&apos;s return on investment, and the common thread is that the full
        test suite was green for every one of them.
      </p>

      <DataTable
        columns={[
          { key: "found", header: "Found", width: "w-[42%]" },
          { key: "impact", header: "Impact" },
        ]}
        rows={[
          {
            id: "wrong-list",
            cells: {
              found: "The eval was scoring the pre-rerank list",
              impact:
                "Made a working feature look worthless — the obvious conclusion would have been to delete the reranker. Once fixed it was worth +12% MRR overall and +33% on normal questions",
            },
            highlight: true,
          },
          {
            id: "hybrid",
            cells: {
              found: "Hybrid retrieval losing to vector-only",
              impact: "Contradicted the design document. Reopened rank-fusion weighting as a live question",
            },
          },
          {
            id: "margin",
            cells: {
              found: "The conditional-rerank threshold was wrong by 4x",
              impact: "A config value that looked tuned and could never fire",
            },
          },
          {
            id: "control",
            cells: {
              found: "A leakage-test control passing vacuously",
              impact: "The security test was green and proving nothing",
            },
          },
          {
            id: "avg",
            cells: {
              found: "Three separate comparisons of non-comparable things",
              impact:
                "Averaged strategies into one row; compared two different lists; scored 8 cases against 41. Each printed a confident number",
            },
          },
          {
            id: "abstain",
            cells: {
              found: "cross_tenant cases were not required to abstain",
              impact: "Eight spurious warnings on the first run, and a weaker assertion than it should have been",
            },
          },
        ]}
      />

      <H2 id="reproducing">Reproducing all of this</H2>
      <DataTable
        columns={[
          { key: "result", header: "Result", width: "w-[38%]" },
          { key: "command", header: "Command" },
          { key: "needs", header: "Needs a key?" },
        ]}
        rows={[
          {
            id: "r1",
            cells: { result: "Retrieval strategies table", command: <code>make eval-retrieval</code>, needs: "No" },
            highlight: true,
          },
          { id: "r2", cells: { result: "Chunking experiment", command: <code>make chunking-experiment</code>, needs: "No" } },
          { id: "r3", cells: { result: "Latency percentiles", command: <code>make eval-retrieval</code>, needs: "No" } },
          { id: "r4", cells: { result: "Faithfulness and citation accuracy", command: <code>make eval</code>, needs: "Yes — the judge is an LLM" } },
          { id: "r5", cells: { result: "Confidence threshold sweep", command: <code>make tune</code>, needs: "No" } },
          { id: "r6", cells: { result: "Cost and live latency", command: "the /admin dashboard", needs: "Yes, to generate traffic" } },
        ]}
        caption="Everything reproducible without a key is reproducible from a fresh clone, because the corpus and its generation cache are committed."
      />

      <p>
        <Link href="/docs/limitations">
          What these numbers do not support, stated before someone quotes them →
        </Link>
      </p>
    </DocPage>
  );
}
