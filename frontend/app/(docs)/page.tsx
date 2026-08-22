import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import DataTable from "@/components/docs/DataTable";
import Figure from "@/components/docs/Figure";
import { ContrastList } from "@/components/docs/StatGrid";
import SystemDiagram from "@/components/docs/diagrams/SystemDiagram";
import { H2, H3 } from "@/components/docs/Prose";
import { ArrowRight, Check } from "@/components/ui/Icon";

/**
 * The overview — and the site's front door.
 *
 * The information architecture changed here: `/` used to be the chat UI, and is
 * now this page. The reasoning is that a stranger's first thirty seconds should
 * establish what the system is, what failure it was built against, and which of
 * its claims are measured — not drop them into an empty text box. The running
 * product is one primary action away, at `/try`.
 *
 * This page does not use the `DocPage` frame, because it needs a hero and a
 * card grid that break out of the reading measure. It keeps `id="doc-content"`
 * so the "On this page" rail still finds its headings.
 */

export const metadata: Metadata = {
  title: "Fishack — grounded, cited, confidence-gated support answers",
  description:
    "A multi-tenant RAG support assistant built without a RAG framework. Hybrid retrieval, " +
    "post-hoc citation validation, a confidence gate that abstains instead of guessing, and a " +
    "65-case evaluation harness that says when it is wrong.",
};

const PROMISE_ROWS = [
  {
    id: "cited",
    cells: {
      clause: <strong>Every claim cited</strong>,
      element: "Inline [n] markers in the answer, each one a button that opens the exact chunk it points at.",
      falsifiable: "A marker pointing at a source the backend never offered renders as a fabrication, in rose, rather than as a working link.",
    },
  },
  {
    id: "verified",
    cells: {
      clause: <strong>Every citation verified</strong>,
      element: "A per-claim verdict inside each source — supports, with the similarity, or weak match.",
      falsifiable: "Validation runs after generation on every answer, and its failures are surfaced rather than suppressed.",
    },
  },
  {
    id: "gated",
    cells: {
      clause: <strong>Confidence-gated</strong>,
      element: "A pill showing the score, the threshold, and which of the two scales the score is on.",
      falsifiable: "The two scales differ by roughly 30x, so a bare number would be a lie. 0.02 is healthy on one and catastrophic on the other.",
    },
  },
  {
    id: "escalates",
    cells: {
      clause: <strong>Escalates instead of guessing</strong>,
      element: "An amber banner with the reason in plain language and a ticket id.",
      falsifiable: "The ticket carries the conversation and the top ten sources with their scores, so a human does not repeat the search that just failed.",
    },
  },
  {
    id: "isolated",
    cells: {
      clause: <strong>Tenant-isolated</strong>,
      element: "A tenant switcher, and an answer that visibly declines to cross.",
      falsifiable: "Switching clears the conversation, and says so before the click — carrying history across would feed one tenant's answers into another's prompt.",
    },
  },
];

const NEXT_CARDS = [
  {
    href: "/docs/quickstart",
    title: "Quickstart",
    body: "Three commands to a running stack with the corpus ingested, and what each one is actually doing.",
  },
  {
    href: "/docs/results",
    title: "Measured results",
    body: "Every number this project claims, the command that reproduces it, and the caveat that bounds it.",
  },
  {
    href: "/docs/field-notes",
    title: "Field notes",
    body: "Seven bugs that kept the whole test suite green while breaking the system.",
  },
  {
    href: "/docs/decisions",
    title: "Decision record",
    body: "Twenty-eight ADRs: context, decision, alternatives, and why each was rejected.",
  },
];

export default function OverviewPage() {
  return (
    <div id="doc-content" className="pb-4">
      {/* ------------------------------------------------------------ hero -- */}
      <header className="border-b border-line pb-10">
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ocean-600">
          Documentation · Overview
        </p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl">
          A support assistant that would rather say nothing than say something wrong.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-500">
          Fishack answers questions from one customer&apos;s own documentation and refuses when
          that corpus cannot support an answer. Every claim carries a citation, every citation is
          checked after the answer is written, and a confidence gate escalates to a human instead
          of guessing.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link
            href="/try"
            className="group inline-flex items-center gap-2 rounded-md bg-ocean-600 px-4 py-2.5
                       text-sm font-medium text-white shadow-card transition-colors hover:bg-ocean-700"
          >
            Try it
            <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/docs/quickstart"
            className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-4 py-2.5
                       text-sm font-medium text-slate-700 transition-colors hover:border-line-strong hover:bg-slate-50"
          >
            Run it locally
          </Link>
          <Link
            href="/docs/architecture"
            className="inline-flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium
                       text-slate-600 transition-colors hover:text-ocean-700"
          >
            Read the architecture
          </Link>
        </div>

        <ul className="mt-8 flex flex-wrap gap-x-2 gap-y-2">
          {[
            "multi-tenant",
            "hybrid retrieval",
            "cited and validated",
            "confidence-gated",
            "no RAG framework",
            "369 tests + 23 integration",
            "65-case eval harness",
          ].map((chip) => (
            <li
              key={chip}
              className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface
                         px-2.5 py-1 text-xs text-slate-600"
            >
              <Check size={11} className="text-emerald-600" />
              {chip}
            </li>
          ))}
        </ul>
      </header>

      <div className="prose-doc mt-10 max-w-prose">
        <H2 id="the-problem">The failure this was built against</H2>
        <p>
          A support answer that <em>sounds</em> right is worse than no answer, because nobody
          checks it. The failure mode of a documentation assistant is not silence — it is a fluent
          paragraph assembled from two pages that contradict each other, with a version number
          silently dropped and no way for the reader to tell.
        </p>
        <p>
          Fishack is built for a fictional B2B analytics and billing SaaS called{" "}
          <strong>Flowlytics</strong>, whose corpus contains the conflicts a real one does: product
          docs that disagree with a changelog, error codes one digit apart with opposite fixes, and
          support tickets whose question and resolution live in different places. Every defence in
          the system exists because one of those cases defeated the version before it.
        </p>

        <Callout kind="note" title="Two tenants, two corpora">
          <p>
            <code>acme</code> and <code>globex</code> each have their own documents, changelog and
            tickets, with deliberate near-duplicates across them so that the tenant predicate is
            the only thing separating the two. That is what makes the isolation tests meaningful
            rather than vacuous.
          </p>
        </Callout>

        <H2 id="the-promise">The promise, and where you can see it</H2>
        <p>
          The tagline is not marketing copy, it is a specification. Each clause names a property,
          and each property has a UI element whose only job is to make that property observable —
          and, more importantly, falsifiable.
        </p>
      </div>

      <div className="max-w-prose">
        <DataTable
          columns={[
            { key: "clause", header: "Clause", width: "w-[22%]" },
            { key: "element", header: "What proves it" },
            { key: "falsifiable", header: "How it could fail visibly" },
          ]}
          rows={PROMISE_ROWS}
          caption="Every row is a behaviour in the running product, not an aspiration. The guided tour walks all five in about three minutes."
        />
      </div>

      <div className="prose-doc mt-10 max-w-none">
        <H2 id="architecture">How it fits together</H2>
      </div>
      <Figure caption="Four bands: the request plane, the query pipeline, the data and model plane, and the two offline systems that feed it. Ingestion and the eval harness never serve a request — they produce the corpus the pipeline reads and the scorecard that says whether it got worse.">
        <SystemDiagram />
      </Figure>

      <div className="prose-doc mt-10 max-w-prose">
        <p>
          Everything on that diagram is written out. There is no LangChain, no LlamaIndex, and no
          vendor SDK anywhere in the system: retrieval, rank fusion, reranking, prompt assembly,
          citation validation, caching and evaluation are all code in this repository, and every
          LLM provider is raw <code>httpx</code>. That is the point of the project — the
          interesting decisions are precisely the ones a framework would have made for you, and
          they are the ones worth being able to defend.
        </p>

        <H2 id="what-it-is-not">What it deliberately is not</H2>
        <ContrastList
          items={[
            {
              claim: "A general chatbot",
              because:
                "An out-of-corpus question gets an abstention and zero LLM calls — the confidence gate sits before generation, so nothing is spent on a question the corpus cannot answer.",
            },
            {
              claim: "A framework demonstration",
              because:
                "No RAG framework is used. Every ranking function, threshold and prompt is in the repository, and each one has a comment saying how its value was chosen.",
            },
            {
              claim: "A benchmark claim",
              because: (
                <>
                  Every number here is measured on one 65-case golden set over one AI-written
                  corpus, and each one says so.{" "}
                  <Link href="/docs/limitations">The limitations page</Link> states what that does
                  and does not support.
                </>
              ),
            },
            {
              claim: "Production-tuned",
              because:
                "The cross-encoder costs more than the entire latency budget on this hardware, so it ships behind a flag. The measurement that justifies dropping it is a stronger artefact than shipping it on would have been.",
            },
          ]}
        />

        <H2 id="headline-results">What the evaluation found</H2>
        <p>
          The harness lives in <code>fishnet/</code> and is the most useful thing this project
          produced, because it contradicted its own design document. Three findings are worth
          arriving with.
        </p>

        <H3 id="hybrid-lost">Hybrid retrieval lost to vector-only on this corpus</H3>
      </div>

      <div className="max-w-prose">
        <DataTable
          columns={[
            { key: "arm", header: "Arm" },
            { key: "recall5", header: "recall@5", numeric: true },
            { key: "mrr", header: "MRR", numeric: true },
            { key: "latency", header: "mean latency", numeric: true },
          ]}
          rows={[
            { id: "bm25", cells: { arm: "BM25 only", recall5: "0.747", mrr: "0.677", latency: "10 ms" } },
            {
              id: "vector",
              cells: { arm: "Vector only", recall5: "0.938", mrr: "0.820", latency: "40 ms" },
              highlight: true,
            },
            { id: "rrf", cells: { arm: "BM25 + vector (RRF)", recall5: "0.910", mrr: "0.768", latency: "50 ms" } },
            { id: "rrf-rr", cells: { arm: "BM25 + vector + reranker", recall5: "0.895", mrr: "0.863", latency: "1,700 ms" } },
            { id: "vec-rr", cells: { arm: "Vector + reranker", recall5: "0.915", mrr: "0.893", latency: "3,300 ms" } },
          ]}
          caption="make eval-retrieval · 65 cases across both tenants · retrieval only, so no LLM calls and fully reproducible."
        />
      </div>

      <div className="prose-doc mt-6 max-w-prose">
        <p>
          The sharpest single case: on <em>&ldquo;how long until my events show up in the
          dashboard?&rdquo;</em> the correct chunk sat at rank 7 under vector search and rank 20
          after fusion. Only the top 8 candidates reach the reranker, so blending pushed the right
          answer <strong>out of the reranker&apos;s reach</strong>. The vector arm recovered it;
          the hybrid arm could not.
        </p>

        <Callout kind="caveat">
          <p>
            This corpus is AI-written prose: smooth and semantically easy, which flatters vector
            search. Real documentation full of internal jargon and codenames would favour the
            keyword leg considerably more. This is a result about <em>this corpus</em>, not a
            result about retrieval.
          </p>
        </Callout>

        <H3 id="chunking-won">Per-source chunking beat fixed windows, decisively</H3>
        <p>
          The same corpus was ingested twice — once with the three per-source chunkers, once with
          fixed 1,600-character windows — under shadow tenants and scored identically. Naive
          chunking loses <strong>45% of multi-turn answers entirely</strong>: not ranked lower,
          absent from the top 20. It cuts a ticket&apos;s question away from its resolution and
          strips the heading context that tells a chunk what it is about.
        </p>

        <H3 id="reranker-costs">The cross-encoder costs more than the whole latency budget</H3>
        <p>
          Mean 1.7&ndash;3.3 seconds on a 12-thread CPU, against a target of P95 under three
          seconds <em>for the entire request</em>. Buying +0.073 MRR for +3.3 seconds is a real
          product decision, and the numbers to make it are now on the table rather than in a hunch.
          On a GPU or a hosted reranker that is roughly 200 ms and an obvious yes.
        </p>

        <p>
          <Link href="/docs/results">All measured results, with their provenance and caveats →</Link>
        </p>

        <H2 id="where-next">Where to go next</H2>
      </div>

      <div className="mt-4 grid max-w-prose gap-3 sm:grid-cols-2">
        {NEXT_CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group rounded-lg border border-line bg-surface px-4 py-3.5 transition-colors
                       hover:border-ocean-300 hover:bg-ocean-50/40"
          >
            <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
              {card.title}
              <ArrowRight
                size={13}
                className="text-slate-300 transition-all group-hover:translate-x-0.5 group-hover:text-ocean-500"
              />
            </span>
            <span className="mt-1 block text-xs leading-relaxed text-slate-500">{card.body}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
