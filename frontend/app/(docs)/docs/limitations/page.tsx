import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/limitations")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function LimitationsPage() {
  return (
    <DocPage
      href="/docs/limitations"
      eyebrow="Reference"
      title="Limitations"
      lead="Read this before quoting a number from anywhere else on this site. Nothing here is a defect report — these are the boundaries of what was built and what was measured, stated where someone will find them rather than discovered later."
    >
      <H2 id="measurement">What the numbers do not support</H2>
      <DataTable
        columns={[
          { key: "limit", header: "Limitation", width: "w-[32%]" },
          { key: "detail", header: "Detail" },
        ]}
        rows={[
          {
            id: "corpus",
            cells: {
              limit: "The corpus is AI-written prose",
              detail:
                "Smooth, semantically coherent, and easy for an embedding model. This flatters vector search and understates what a keyword leg is worth on real documentation full of internal jargon, codenames and inconsistent phrasing. Every retrieval result here is a result about THIS corpus.",
            },
            highlight: true,
          },
          {
            id: "n",
            cells: {
              limit: "65 cases is enough to catch regressions, not to make a claim",
              detail:
                "Per-type case counts run from 8 to 16, which is small enough that a single case moves the average by a visible amount. A 3-point recall difference is inside the noise.",
            },
          },
          {
            id: "hardware",
            cells: {
              limit: "Reranker latency is a property of this laptop",
              detail:
                "Measured on a 12-thread CPU with no GPU. A hosted reranker or a GPU changes that decision entirely — roughly 200 ms instead of 1.7–3.3 seconds, at which point the trade is obviously worth taking.",
            },
          },
          {
            id: "judge",
            cells: {
              limit: "Judge scores are a noisy estimator",
              detail:
                "The same answer scores differently on consecutive judgements. Quality metrics therefore carry a 5% tolerance, and a single run's faithfulness score should be read as a trend rather than a measurement.",
            },
          },
          {
            id: "cost",
            cells: {
              limit: "Cost figures are modelled, not billed",
              detail:
                "Real spend is $0 on free tiers. Virtual cost prices each request at paid-API list prices from a table snapshotted in July 2026, which drifts as providers change pricing.",
            },
          },
          {
            id: "synthetic",
            cells: {
              limit: "Synthetic generation trades difficulty for verifiability",
              detail:
                "Declaring every fact in code is what makes ground truth trustworthy. It also makes the corpus easier than a real one — both halves of that trade are real.",
            },
          },
        ]}
      />

      <H2 id="capability">What the system does not do</H2>
      <DataTable
        columns={[
          { key: "gap", header: "Gap", width: "w-[32%]" },
          { key: "detail", header: "What it means, and what would fix it" },
        ]}
        rows={[
          {
            id: "entailment",
            cells: {
              gap: "Citation validation is similarity, not entailment",
              detail:
                "It catches a citation pointing at an unrelated chunk. It cannot catch a citation pointing at a chunk that says the OPPOSITE — 'retries cap at 3' and 'retries cap at 5' are highly similar, and that is exactly the stale-data failure this corpus plants. Fixing it needs an NLI model, which is another ~1.4 GB on a CPU already spending seconds on reranking.",
            },
            highlight: true,
          },
          {
            id: "sentence",
            cells: {
              gap: "Attribution is claim-to-chunk, not sentence-to-sentence",
              detail:
                "The UI maps each claim to the chunk it cited, because chunks are what retrieval returns and what validation checks. Sentence-level attribution needs the same missing entailment model, scoring each answer sentence against each sentence of the chunk.",
            },
          },
          {
            id: "assembly",
            cells: {
              gap: "Nothing catches a claim assembled correctly from two chunks that should not be combined",
              detail:
                "Each half is supported; the conjunction is not. The prompt's conflict rule and the contested-source flag mitigate this partially, and neither is a check.",
            },
          },
          {
            id: "auth",
            cells: {
              gap: "There is no authentication",
              detail:
                "The tenant arrives in the request body, which is correct for a demonstration with no login and a trivial cross-tenant read in production. The statistics endpoint is open unless a token is set. Both are documented at every point they matter, and a note is not a control.",
            },
            highlight: true,
          },
          {
            id: "rls",
            cells: {
              gap: "Isolation is enforced in application code, not in the database",
              detail:
                "Four layers make the unsafe query unwritable in Python. A raw psql session, or a future non-Python consumer, is not covered. Row-level security belongs underneath all of it.",
            },
          },
          {
            id: "conv",
            cells: {
              gap: "Conversations do not persist",
              detail:
                "History lives in the client. Traces are grouped by conversation id for observability, but there is no cross-device resume — that would need a sessions service in front of the stateless core.",
            },
          },
        ]}
      />

      <H2 id="open">Open questions, with evidence that they are open</H2>
      <p>
        These are not gaps in the writeup — they are places where a measurement exists that
        contradicts a current setting, and the follow-up experiment has not been run.
      </p>

      <DataTable
        columns={[
          { key: "q", header: "Question", width: "w-[30%]" },
          { key: "evidence", header: "The evidence" },
          { key: "next", header: "Next step" },
        ]}
        rows={[
          {
            id: "weights",
            cells: {
              q: "Should the fusion weights stay equal?",
              evidence:
                "Weights were avoided on principle to escape per-corpus tuning. Evaluation then measured the keyword leg actively harming multi-turn recall — MRR 0.159 against vector's 0.625 — while equal-weight fusion let that harm win the average.",
              next: "Sweep the keyword weight at 0.5 against the golden set. Not yet run.",
            },
            highlight: true,
          },
          {
            id: "margin",
            cells: {
              q: "Is the fusion margin a usable ambiguity signal at all?",
              evidence:
                "Conditional reranking is implemented, tested, and has never fired on this corpus at either threshold value. Fusion compresses scores hard by design, so the dynamic range may simply be too narrow to threshold on.",
              next: "Sweep 0.03–0.15; if nothing trades latency for acceptable recall, gate on raw per-leg scores instead and accept losing cross-query comparability.",
            },
          },
          {
            id: "thresholds",
            cells: {
              q: "Are the two confidence thresholds right?",
              evidence: "Both are labelled as guesses in the config file. Neither has been swept.",
              next: "`make tune` against the golden set, per scale.",
            },
          },
          {
            id: "semantic",
            cells: {
              q: "Does the semantic cache cost recall?",
              evidence:
                "0.95 is a design number the guardrails made survivable, not one that was validated. The harness can now measure it.",
              next: "Run the golden set with the semantic cache warm and compare.",
            },
          },
          {
            id: "rerank-k",
            cells: {
              q: "Is rerank_input_top_k = 8 leaving quality on the table?",
              evidence:
                "Eight was chosen for latency. A chunk fusion ranked ninth that the cross-encoder would have promoted to first is now unreachable.",
              next: "Sweep 8 against 20. If recall@5 barely moves, the latency was free.",
            },
          },
        ]}
      />

      <Callout kind="note" title="Why these are on the site rather than in a private list">
        <p>
          A project page that lists only what worked is a sales document. The two most interesting
          findings here — that hybrid retrieval lost on this corpus, and that a shipped feature has
          never once fired — are both negative results, and both are more informative than the
          positive ones. Recording the open questions with the evidence that opened them is the same
          instinct applied forward.
        </p>
      </Callout>

      <H2 id="production">What would have to change for production</H2>
      <DataTable
        columns={[
          { key: "area", header: "Area", width: "w-[26%]" },
          { key: "change", header: "Change" },
        ]}
        rows={[
          {
            id: "auth-prod",
            cells: {
              area: "Authentication",
              change:
                "Tenant from an authenticated session or JWT claim; the scope constructed from the auth context. SSO with an admin role on the statistics endpoint, with every access audited.",
            },
          },
          {
            id: "rls-prod",
            cells: {
              area: "Isolation",
              change: "Row-level security under the application-level scope, so non-Python consumers are covered too.",
            },
          },
          {
            id: "rerank-prod",
            cells: {
              area: "Reranking",
              change:
                "A hosted reranker or a GPU, at which point rerank_input_top_k would sit at 20+ and nobody would think about it. Or ONNX Runtime instead of PyTorch, cutting resident memory from ~800 MB to ~100 MB.",
            },
            highlight: true,
          },
          {
            id: "bm25-prod",
            cells: {
              area: "Keyword retrieval",
              change:
                "A real BM25 engine at scale or with heterogeneous document lengths — which also removes the string surgery currently done on the rendered tsquery.",
            },
          },
          {
            id: "types-prod",
            cells: {
              area: "API types",
              change:
                "Generate the frontend types from the OpenAPI schema in CI. A hand-written type that silently drifts is worse than no type, because TypeScript will confidently vouch for it.",
            },
          },
          {
            id: "migrations-prod",
            cells: {
              area: "Migrations",
              change: "A migration framework, for autogenerate-with-review, downgrade testing and merge safety across a team.",
            },
          },
        ]}
      />

      <p>
        Every one of these is marked in the source with a production note at the point it applies,
        rather than collected only here — the person who needs it is reading the module, not this
        page.
      </p>

      <p>
        <Link href="/docs/glossary">Glossary →</Link>
      </p>
    </DocPage>
  );
}
