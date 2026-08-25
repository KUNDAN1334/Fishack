import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/evaluation")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function EvaluationPage() {
  return (
    <DocPage
      href="/docs/evaluation"
      eyebrow="Evaluation"
      title="The eval harness"
      lead="65 cases across six types, ground truth expressed as source locators rather than chunk ids, four metrics whose arithmetic can be checked by hand, an LLM judge on a separate model and provider chain, and a CI gate with two tolerances — 5% on quality and zero on correctness."
    >
      <H2 id="why">Why an eval harness is the deliverable</H2>
      <p>
        Without one, every claim about a RAG system is an anecdote. &ldquo;It seems better&rdquo;
        after a chunker change is indistinguishable from the four queries you happened to try. More
        importantly, a system that can only confirm its own design is not being measured — and this
        harness earned its place by <strong>contradicting the design document that specified
        it</strong>, twice.
      </p>

      <H2 id="golden-set">The golden set</H2>
      <p>
        65 cases, derived from the corpus specification and then hand-edited. Six types, each of
        which exercises a different component.
      </p>

      <DataTable
        columns={[
          { key: "type", header: "Case type", width: "w-[22%]" },
          { key: "n", header: "Cases", numeric: true },
          { key: "tests", header: "What it tests" },
        ]}
        rows={[
          { id: "normal", cells: { type: <code>normal</code>, n: "16", tests: "Baseline — a direct question answered from one source" } },
          {
            id: "oos",
            cells: {
              type: <code>out_of_scope</code>,
              n: "16",
              tests: "The confidence gate and the abstention path. MUST abstain",
            },
            highlight: true,
          },
          {
            id: "ident",
            cells: {
              type: <code>exact_identifier</code>,
              n: "9",
              tests: "The keyword leg's entire justification. If these fail, keyword search is worthless",
            },
          },
          { id: "multi", cells: { type: <code>multi_turn</code>, n: "8", tests: "Whether query rewriting works" } },
          { id: "stale", cells: { type: <code>stale_conflict</code>, n: "8", tests: "Versioning and the conflict rule in the prompt" } },
          {
            id: "cross",
            cells: {
              type: <code>cross_tenant</code>,
              n: "8",
              tests: "Tenant isolation. MUST NOT leak, and must also abstain",
            },
            highlight: true,
          },
        ]}
        caption="Every metric is reported per case type as well as overall — see below for why that is not a presentation choice."
      />

      <Callout kind="caution" title="An aggregate metric hides the interesting failure">
        <p>
          Suppose overall recall@5 comes out at 0.85. That looks healthy. It is also exactly what
          you would see if normal questions scored 0.98 across sixteen cases and identifier queries
          scored 0.20 across nine. One number is lying to you.
        </p>
        <p>
          &ldquo;Recall is 0.85&rdquo; is a number. &ldquo;Recall is 0.98 on normal questions and
          0.20 on identifier queries&rdquo; is a finding, and it names the component to fix. The
          per-type breakdown caught precisely that, and it was the whole justification for keeping a
          keyword leg.
        </p>
      </Callout>

      <H3 id="case-shape">What a case carries</H3>
      <CodeBlock
        language="python"
        filename="fishnet/models.py"
        code={`class GoldenCase(BaseModel):
    case_id: str                    # "GC-0041" — stable, human-assigned
    case_type: CaseType
    tenant_id: str
    query: str
    history: list[dict[str, str]]   # prior turns, for multi_turn cases

    expected_sources: list[SourceLocator]   # NOT chunk ids — see below

    reference_answer: str           # prose: "a good answer looks like this"
    must_contain: list[str]         # ["5"] — literals that MUST appear
    forbidden_text: str | None      # cross_tenant: this string must never appear
    notes: str`}
      />
      <p>
        Two fields are each the result of one decision. <code>reference_answer</code> is prose
        rather than an exact string, because exact-match scoring on generated text measures{" "}
        <em>phrasing</em>, not correctness — &ldquo;The retry limit is 5&rdquo; and &ldquo;Retries
        cap at 5&rdquo; are both right. And <code>must_contain</code> is deterministic, which is the
        cheap complement to a noisy judge: it catches a fluent answer that quietly omits the actual
        figure. In a stale-data case, <code>must_contain: [&quot;5&quot;]</code> <em>is</em> the
        point — plausibly discussing retries is not enough.
      </p>

      <H3 id="locators">Stable locators are the harness&apos;s most important idea</H3>
      <p>
        Ground truth is a <code>SourceLocator</code> — <code>{`{source_type, slug, heading}`}</code>{" "}
        for docs, an entry id for the changelog, a ticket id for tickets — resolved to chunk ids at
        the start of every run.
      </p>

      <DataTable
        columns={[
          { key: "option", header: "Ground truth as…", width: "w-[26%]" },
          { key: "problem", header: "Consequence" },
        ]}
        rows={[
          {
            id: "uuid",
            cells: {
              option: "Chunk UUIDs",
              problem:
                "Simplest to compute, and wrong in a way that surfaces weeks later. Re-ingesting invalidates the whole golden set silently: every case points at rows that no longer exist, recall drops to zero, and it presents as a catastrophic retrieval regression with no cause",
            },
          },
          {
            id: "hash",
            cells: {
              option: "Content hashes",
              problem:
                "Stable across re-ingest only while the chunker produces byte-identical text. Breaks the moment chunk boundaries move — which is what the chunking experiment does",
            },
          },
          {
            id: "locator",
            cells: {
              option: "Source locators",
              problem:
                "Expresses ground truth in terms of the SOURCE, which both chunking arms share. Without this the chunking experiment is not awkward, it is impossible",
            },
            highlight: true,
          },
        ]}
      />

      <p>
        Resolution runs before any retrieval or generation, so a stale golden set fails in seconds
        rather than after twenty minutes of LLM calls. Unresolved locators are reported loudly and
        never dropped: a locator matching nothing means the golden set and the corpus have diverged,
        and without a signal that looks like a recall regression.
      </p>

      <H2 id="metrics">Four metrics, each with its arithmetic in the docstring</H2>
      <DataTable
        columns={[
          { key: "metric", header: "Metric", width: "w-[18%]" },
          { key: "asks", header: "The question it answers" },
          { key: "detail", header: "The decision inside it" },
        ]}
        rows={[
          {
            id: "recall",
            cells: {
              metric: "recall@k",
              asks: "What fraction of the chunks that should have been retrieved made the top k?",
              detail:
                "Returns 1.0 when nothing was expected. An out-of-scope case had nothing to find, so nothing was missed — returning 0.0 would drag the aggregate down for the behaviour we WANT",
            },
            highlight: true,
          },
          {
            id: "precision",
            cells: {
              metric: "precision@k",
              asks: "How much of the top k was actually relevant?",
              detail:
                "Divides by min(k, retrieved), not k — dividing by k punishes a system for returning three excellent results when the corpus only holds three. That is a penalty for a small corpus, not for being wrong",
            },
          },
          {
            id: "mrr",
            cells: {
              metric: "MRR",
              asks: "How high did the FIRST correct chunk land?",
              detail:
                "Two systems can share a recall@5 while one puts the answer first and the other fifth. Only MRR sees that, and language models are position-sensitive, so the difference is real",
            },
          },
          {
            id: "hit",
            cells: {
              metric: "hit@k",
              asks: "Did any correct chunk make the top k? Yes or no",
              detail:
                "Coarser than recall and sometimes the more honest question. It became the chunking experiment's headline metric because it is immune to the measurement artefact described there",
            },
          },
        ]}
      />

      <Callout kind="note" title="Macro-averaged, over cases">
        <p>
          The mean is taken over <em>cases</em>, not over retrieved chunks, so every case carries
          equal weight and one case expecting six chunks cannot dominate fifty expecting one.
          Micro-averaging would let the shape of the corpus drive the headline number rather than
          the quality of the system.
        </p>
      </Callout>

      <H2 id="judge">The LLM judge</H2>
      <p>
        Faithfulness, citation accuracy and answer relevance cannot be computed arithmetically, so
        they are scored by a model. Three things about how make the scores worth reading.
      </p>

      <DataTable
        columns={[
          { key: "choice", header: "Choice", width: "w-[30%]" },
          { key: "why", header: "Why" },
        ]}
        rows={[
          {
            id: "model",
            cells: {
              choice: "A different, larger model",
              why: "A model judging its own output shares its blind spots. If the generator misreads a chunk, the same model asked 'is this faithful?' tends to misread it identically and say yes. The failures are correlated, so it measures agreement with itself rather than correctness",
            },
          },
          {
            id: "chain",
            cells: {
              choice: "A separate provider chain, reversed",
              why: "Sharing the chain means a rate-limited judge silently falls back onto the exact model it is grading — the correlated-failure problem reintroduced through the back door, invisibly",
            },
            highlight: true,
          },
          {
            id: "rubric",
            cells: {
              choice: "An explicit rubric with named criteria and anchors",
              why: "'Rate this 1-10' produces numbers that drift between runs and cannot be reasoned about. Named criteria with stated anchor points are reproducible enough to diff, and inspectable — when a score looks wrong you can read the rubric and see whether the judge or the rubric was at fault",
            },
          },
          {
            id: "reference-last",
            cells: {
              choice: "The reference answer goes LAST in the prompt",
              why: "Placed early it gets anchored on, and the judge scores similarity-to-reference rather than faithfulness-to-context — rewarding paraphrase over grounding",
            },
          },
        ]}
      />

      <CodeBlock
        language="text"
        filename="fishnet/judge.py — the rubric, and one rule specific to this system"
        code={`1. FAITHFULNESS — is every factual claim in ANSWER supported by CONTEXT?
   1.0  every claim traceable to the context
   0.5  mostly supported, at least one claim goes beyond it
   0.0  claims the context does not support at all
   Judge against CONTEXT only, never against your own knowledge.

2. CITATION_ACCURACY — does each [n] marker point at a source that actually
   supports the claim it is attached to? A claim with no marker counts against.

3. ANSWER_RELEVANCE — does ANSWER address the QUESTION?
   An abstention scores 1.0 when the context genuinely lacks the answer, 0.0 when
   it does not.

RULE: if sources conflict and ANSWER follows the newer one AND states that the
older one disagrees, that is full marks on faithfulness. It is the system's
designed behaviour, not a contradiction.`}
      />
      <p>
        Without that last rule the judge scores the system&apos;s best feature as a bug.
      </p>

      <Callout kind="caveat" title="Judge scores are a noisy estimator, not a measurement">
        <p>
          The same answer scores differently on consecutive judgements. That is why quality metrics
          carry a 5% tolerance and hard assertions carry none, and why a skipped judgement is
          excluded from the average rather than counted as 0.0 — averaging &ldquo;not
          measured&rdquo; with &ldquo;measured badly&rdquo; produces a number that means neither.
        </p>
      </Callout>

      <H2 id="assertions">Hard assertions</H2>
      <p>
        Fundamentally different from every other number here: binary, and with no tolerance band.
      </p>

      <DataTable
        columns={[
          { key: "assertion", header: "Assertion", width: "w-[28%]" },
          { key: "what", header: "What it catches" },
        ]}
        rows={[
          {
            id: "abstain",
            cells: {
              assertion: <code>must_abstain</code>,
              what: "A confident, fluent, well-cited answer to a question the corpus cannot answer. This is the single failure the whole system exists to prevent, and the only check that measures what the gate, the closed-book prompt and the few-shot abstention examples are jointly trying to produce",
            },
            highlight: true,
          },
          {
            id: "leak",
            cells: {
              assertion: <code>no_cross_tenant_leak</code>,
              what: "Two independent checks, because there are two ways to fail. A chunk-level check catches a retrieval leak; a text-level check catches content that reached the answer by some OTHER route — a wrongly-namespaced cache, a prompt-assembly bug, history carried across tenants. The chunk check cannot see those at all",
            },
          },
          {
            id: "fabricated",
            cells: {
              assertion: <code>no_fabricated_citations</code>,
              what: "A [7] marker when only five sources were offered. Unambiguous — no model, no threshold — which is what makes it assertable rather than merely measurable",
            },
          },
          {
            id: "contains",
            cells: {
              assertion: <code>must_contain</code>,
              what: "Required literals. The cheap deterministic complement to the judge's biggest weakness: a fluent answer that quietly omits the actual figure",
            },
          },
        ]}
        caption="Checks that do not apply to a case return nothing and are dropped — '3 of 3 passed' must never include skipped checks."
      />

      <Callout kind="result" title="A bug the first real run caught">
        <p>
          <code>MUST_ABSTAIN_TYPES</code> originally contained only <code>out_of_scope</code>, and
          the first run produced eight spurious warnings. On reflection, <code>cross_tenant</code>{" "}
          has the same semantics: asking tenant A about tenant B&apos;s private document is a
          question A&apos;s corpus cannot answer, and abstaining is correct.
        </p>
        <p>
          Adding it made the check <em>stronger</em>. A cross-tenant case now asserts two things: no
          foreign chunk leaked, <strong>and</strong> the system did not paper over the gap with its
          own similar document. Acme has its own onboarding runbook — answering &ldquo;what does the
          Globex Onboarding Runbook say?&rdquo; from it leaks nothing and is still a lie.
        </p>
      </Callout>

      <H2 id="ci">The CI gate</H2>
      <DataTable
        columns={[
          { key: "kind", header: "", width: "w-[24%]" },
          { key: "quality", header: "Quality metrics" },
          { key: "hard", header: "Hard assertions" },
        ]}
        rows={[
          {
            id: "what",
            cells: {
              kind: <strong>What</strong>,
              quality: "recall@5, recall@20, MRR, faithfulness, citation accuracy",
              hard: "must-abstain, no cross-tenant leak, no fabricated citations",
            },
          },
          {
            id: "shape",
            cells: {
              kind: <strong>Shape</strong>,
              quality: "Continuous, noisy, they trade against each other",
              hard: "Binary",
            },
          },
          {
            id: "tol",
            cells: {
              kind: <strong>Tolerance</strong>,
              quality: "A >5% relative drop against the committed baseline fails",
              hard: "Zero — any failure fails the build",
            },
            highlight: true,
          },
        ]}
      />

      <p>
        There is no acceptable rate of cross-tenant leakage, and a percentage band on a security
        check is exactly how a bug gets absorbed by a quality budget. So the two kinds live in
        separate modules and aggregate separately, with the assertions at the top of the scorecard.
      </p>

      <H3 id="gate-rules">Three rules that matter more than the number</H3>
      <ul>
        <li>
          <strong>Improvements never fail.</strong> Obvious until you write{" "}
          <code>abs(delta) &gt; tolerance</code> and start failing builds for getting better.
        </li>
        <li>
          <strong>No baseline is a pass.</strong> A fresh clone must not block CI, or nobody can
          ever create the first baseline.
        </li>
        <li>
          <strong>Generation metrics are skipped when the judge ran on under 25% of cases.</strong>{" "}
          Comparing a score over eight cases against a baseline over sixty is not a comparison, and
          on a free tier quota-limited runs are common enough that failing on them would train people
          to ignore the gate — which costs more than the regressions it would catch.
        </li>
      </ul>

      <p>
        The baseline is <em>committed</em> rather than taken from the previous run. Committing is a
        deliberate act with a reviewable diff: someone looked at a scorecard and decided it
        represented intended behaviour. Auto-updating from the last run lets quality erode one
        tolerated 4% drop at a time, each individually acceptable, none ever noticed.
      </p>

      <H2 id="running">Running it</H2>
      <CodeBlock
        language="shell"
        code={`make eval-retrieval          # five arms, no LLM calls, under a minute
make eval                    # full harness including the judge, vs the baseline
make chunking-experiment     # naive vs per-source chunking, on shadow tenants
make tune                    # sweep the confidence gate

python -m fishnet.run --sample 10        # a subset, for a fast loop
python -m fishnet.run --resume           # per-case checkpointing, for free-tier quota`}
      />
      <p>
        <code>--resume</code> exists because a full run on a free tier can be interrupted by quota
        exhaustion halfway through, and restarting from zero wastes the calls already spent. Every
        report also carries a snapshot of the configuration that produced it, so a scorecard can be
        read six weeks later without guessing which thresholds were in force.
      </p>

      <p>
        <Link href="/docs/results">Every result the harness has produced →</Link>
      </p>
    </DocPage>
  );
}
