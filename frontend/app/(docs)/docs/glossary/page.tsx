import type { Metadata } from "next";
import type { ReactNode } from "react";

import Callout from "@/components/docs/Callout";
import DocPage from "@/components/docs/DocPage";
import { H2 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/glossary")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/**
 * Terms this documentation uses in a specific sense.
 *
 * The entry rule: a term earns a place only if using it loosely would cause a
 * misreading somewhere else on the site. So "vector" is not here and "score
 * kind" is — because a reader who does not know that two score scales exist
 * will misread every confidence figure in the product.
 */

interface Term {
  term: string;
  definition: ReactNode;
}

interface Group {
  title: string;
  id: string;
  terms: Term[];
}

const GROUPS: Group[] = [
  {
    title: "Retrieval",
    id: "retrieval",
    terms: [
      {
        term: "Leg",
        definition:
          "One of the two independent retrieval paths — keyword or vector. A leg supplies a query fragment and never writes a full query; the tenant scope composes the SQL around it.",
      },
      {
        term: "Candidates vs results",
        definition: (
          <>
            <strong>Candidates</strong> is the fused list before reranking; <strong>results</strong>{" "}
            is what the cross-encoder emitted. Both are kept on every retrieval, because scoring the
            wrong one made a working feature look worthless once already.
          </>
        ),
      },
      {
        term: "Reciprocal rank fusion",
        definition: (
          <>
            Merging two ranked lists by <code>Σ weight / (k + rank)</code> rather than by score.
            Scale-free, so there is no normalisation step to get wrong.
          </>
        ),
      },
      {
        term: "Cross-encoder",
        definition:
          "A model that scores a query and a chunk jointly rather than comparing two independently-computed vectors. More accurate, and impossible to precompute — which is why it costs seconds on a CPU.",
      },
      {
        term: "Margin",
        definition: (
          <>
            <code>(s₁ − s₅) / s₁</code> over fused scores, used to decide whether reranking is worth
            running. On this corpus it turned out to measure &ldquo;was the top five
            unanimous&rdquo;, not &ldquo;how confident is the top result&rdquo;.
          </>
        ),
      },
      {
        term: "Degraded leg",
        definition:
          "A retrieval leg that errored. The request continues on the other leg's results, and the answer says so — it was built on less evidence than usual.",
      },
    ],
  },
  {
    title: "Scores and gating",
    id: "scores",
    terms: [
      {
        term: "Score kind",
        definition: (
          <>
            Which of the two scales a confidence figure is on: <code>rerank</code> (a sigmoid in [0,
            1]) or <code>fused</code> (a fusion score around 0.016–0.033). They differ by roughly
            30x, so a bare number is uninterpretable. Recorded on every trace and shown on every
            confidence pill.
          </>
        ),
      },
      {
        term: "Confidence gate",
        definition:
          "The check that runs BEFORE generation. Below threshold, the pipeline abstains without calling the model at all — which is what makes an out-of-scope question cost zero.",
      },
      {
        term: "Abstention",
        definition:
          "A deliberate refusal to answer, using a fixed sentence that the prompt, the detector and the eval assertions all agree on. It is the system working, and it is never rendered as an error.",
      },
      {
        term: "Escalation",
        definition:
          "The row written whenever the system abstains, carrying the conversation and the top ten retrieved chunks with their scores. Ten rather than five, because 'the right chunk was at rank 7' and 'the right chunk was never retrieved' are different bugs.",
      },
    ],
  },
  {
    title: "Content and versioning",
    id: "content",
    terms: [
      {
        term: "Chunk",
        definition:
          "The unit of retrieval. Sized by source type — a docs section, a changelog entry, or one ticket question-and-resolution pair — never by a fixed character window.",
      },
      {
        term: "Heading path",
        definition: (
          <>
            A docs chunk&apos;s position in the document hierarchy, e.g.{" "}
            <em>Billing &gt; Invoices &gt; Proration</em>. Prepended into the chunk&apos;s content so
            it reaches both the keyword index and the embedding, and stored separately for display.
          </>
        ),
      },
      {
        term: "Source locator",
        definition:
          "How the golden set names a source — a slug and heading, or an entry or ticket id — rather than a chunk UUID. Resolved to chunk ids at the start of every run, which is what makes the chunking experiment possible at all.",
      },
      {
        term: "Superseded",
        definition:
          "A document a changelog entry explicitly retired. Its chunks are marked not-current and become unretrievable, but are never deleted.",
      },
      {
        term: "Contested",
        definition: (
          <>
            A chunk a newer changelog entry contradicts on one <em>fact</em>, while the rest of the
            page stays correct. Both stay live; the chunk is tagged at ingestion, and the UI shows an
            amber &ldquo;superseded in part&rdquo; badge. This is the realistic case — in production
            nobody remembers to mark the old doc.
          </>
        ),
      },
      {
        term: "Shadow tenant",
        definition:
          "A throwaway tenant used to ingest the same corpus a second way, so two chunking strategies can be scored side by side against the same golden set.",
      },
    ],
  },
  {
    title: "Generation and validation",
    id: "generation",
    terms: [
      {
        term: "Closed-book",
        definition:
          "The model sees the retrieved chunks and nothing else, and is instructed to abstain rather than answer from its own knowledge.",
      },
      {
        term: "Claim",
        definition:
          "One sentence of the answer, treated as the unit of validation. A claim citing two sources is supported if EITHER backs it, because the prompt explicitly asks the model to cite both sides of a conflict.",
      },
      {
        term: "Grounding rate",
        definition:
          "The fraction of an answer's claims that matched the source they cited. Precomputed onto the trace row so the dashboard and the triage script cannot disagree about it.",
      },
      {
        term: "Fabricated citation",
        definition:
          "A [n] marker pointing at a source index the backend never offered. Flagged in rose in the answer text rather than suppressed — the answer may still be correct, and hiding the discrepancy would be its own failure.",
      },
      {
        term: "Query rewriting",
        definition:
          "Turning a follow-up into a standalone question using recent history. Skipped entirely on the first turn, and its output is validated — the dominant failure of a rewriting prompt is that the model answers the question instead.",
      },
    ],
  },
  {
    title: "Caching and cost",
    id: "caching",
    terms: [
      {
        term: "Exact hit vs semantic hit",
        definition:
          "An exact hit is the same question asked again. A semantic hit is a DIFFERENT question that embedded close enough — which the reader deserves to know while judging whether the answer fits.",
      },
      {
        term: "Identifier guard",
        definition:
          "The rule that keeps queries containing error codes, versions, status codes, ticket ids or endpoint paths out of the semantic cache — on write as well as read. Two error codes mean nearly the same thing and have opposite answers.",
      },
      {
        term: "Active invalidation",
        definition:
          "Deleting exactly the cached answers built on chunks a re-ingest changed, via a chunk-to-keys reverse index — rather than wiping the tenant's cache or waiting for a TTL.",
      },
      {
        term: "Virtual cost",
        definition: (
          <>
            What the observed token usage <em>would</em> cost at paid-API list prices. Real spend is
            $0 on free tiers. The label travels with the figure everywhere, because detached from it
            the number reads as a bill.
          </>
        ),
      },
    ],
  },
  {
    title: "Evaluation",
    id: "evaluation",
    terms: [
      {
        term: "Golden set",
        definition:
          "65 cases across six types, derived from the corpus specification and hand-edited. Ground truth is only trustworthy because every fact in the corpus was declared in code rather than generated.",
      },
      {
        term: "Arm",
        definition:
          "One configuration under comparison — 'vector only', 'BM25 + vector + reranker'. Two arms are only comparable if they were scored over the same cases and the same list.",
      },
      {
        term: "Hard assertion",
        definition:
          "A binary correctness check — must-abstain, no cross-tenant leak, no fabricated citations — with zero tolerance, kept separate from quality metrics so a 5% quality budget cannot absorb a security bug.",
      },
      {
        term: "Macro-averaging",
        definition:
          "Taking the mean over CASES rather than over retrieved chunks, so one case expecting six chunks cannot dominate fifty expecting one. Micro-averaging would let the corpus shape drive the headline number.",
      },
      {
        term: "Baseline",
        definition:
          "A committed scorecard the CI gate compares against. Committed rather than taken from the previous run, because auto-updating lets quality erode one tolerated 4% drop at a time.",
      },
    ],
  },
];

export default function GlossaryPage() {
  return (
    <DocPage
      href="/docs/glossary"
      eyebrow="Reference"
      title="Glossary"
      lead="Terms this documentation uses in a specific sense. A term earns a place here only if using it loosely would cause a misreading somewhere else on the site."
    >
      <Callout kind="note" title="The one to read first">
        <p>
          <strong>Score kind.</strong> This system produces two confidence scales roughly 30x apart,
          and <span className="figure">0.02</span> is healthy on one and catastrophic on the other.
          Every confidence figure in the product carries its scale for that reason, and a reader who
          skips this term will misread all of them.
        </p>
      </Callout>

      {GROUPS.map((group) => (
        <section key={group.id}>
          <H2 id={group.id}>{group.title}</H2>
          <dl className="!mt-4 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
            {group.terms.map((entry) => (
              <div
                key={entry.term}
                className="grid gap-1 px-4 py-3 sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-6"
              >
                <dt className="text-sm font-semibold text-slate-900">{entry.term}</dt>
                <dd className="text-sm leading-relaxed text-slate-600">{entry.definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </DocPage>
  );
}
