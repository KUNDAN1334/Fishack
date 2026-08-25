import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/generation")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function GenerationPage() {
  return (
    <DocPage
      href="/docs/generation"
      eyebrow="Architecture"
      title="Generation and citations"
      lead="A gate that decides whether to call the model at all, a closed-book prompt that must cite, and a post-hoc validator that checks every claim against the source it named — with the hole in that check stated at every call site rather than buried in a docstring."
    >
      <H2 id="gate">The confidence gate</H2>
      <p>
        The gate sits <strong>before</strong> generation, which is what makes an out-of-scope
        question cost zero LLM calls rather than one wasted one. It reads the top retrieved
        result&apos;s score and compares it against a threshold.
      </p>
      <p>
        The complication is that there are two thresholds, because there are two score scales
        roughly 30x apart: the reranker&apos;s sigmoid in [0, 1] and the fusion score around
        0.016–0.033.
      </p>

      <DataTable
        columns={[
          { key: "setting", header: "Threshold", width: "w-[32%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "applies", header: "Applies when" },
        ]}
        rows={[
          {
            id: "rerank",
            cells: {
              setting: <code>confidence_threshold_rerank</code>,
              value: "0.45",
              applies: "A reranker score is present on the top result",
            },
          },
          {
            id: "fused",
            cells: {
              setting: <code>confidence_threshold_fused</code>,
              value: "0.015",
              applies: "Reranking did not run — the score is a fusion score",
            },
          },
        ]}
        caption="Both are provisional and labelled so in config. `make tune` sweeps them against the golden set."
      />

      <p>
        A single threshold would be calibrated for at most one scale and silently wrong for the
        other. Set for the reranker it would abstain on literally everything unreranked; set for
        fusion it would pass everything reranked. Both failures present as &ldquo;the gate is not
        working&rdquo; and neither points at the cause.
      </p>

      <Callout kind="note" title="Which scale is read from the data, not from configuration">
        <p>
          Whether reranking actually ran depends on the conditional gate&apos;s margin, on the
          reranker being loaded at all, and on the candidate count. Configuration knows the{" "}
          <em>intent</em>; only the result knows what happened. The score kind is then recorded on
          the trace and shown in the UI, because <code>top_score = 0.02</code> is uninterpretable
          six weeks later — it is a healthy fusion score and a catastrophic reranker score, and a
          trace that cannot be read is not observability.
        </p>
      </Callout>

      <H2 id="rewriting">Query rewriting</H2>
      <p>
        A follow-up like &ldquo;what about the backoff?&rdquo; is not a searchable query. Rewriting
        turns it into a standalone question using the last six turns, at temperature 0.0.
      </p>

      <H3 id="rewrite-rules">Four rules that make it safe</H3>
      <DataTable
        columns={[
          { key: "rule", header: "Rule", width: "w-[30%]" },
          { key: "why", header: "Why" },
        ]}
        rows={[
          {
            id: "skip",
            cells: {
              rule: "Skipped entirely on the first turn",
              why: "A question with no conversation behind it is standalone by definition. Rewriting could only paraphrase, at the cost of a round trip and a chance to mangle an error code — and most support sessions are a single turn, so this is not a micro-optimisation",
            },
          },
          {
            id: "validated",
            cells: {
              rule: "The output is validated before use",
              why: "The dominant failure of a rewriting prompt is that the model ANSWERS the question instead of rewriting it. An answer silently substituted for a query means searching the corpus for the text of a hallucinated response — a spectacular retrieval bug that raises nothing",
            },
            highlight: true,
          },
          {
            id: "data",
            cells: {
              rule: "History is rendered as data, not replayed as turns",
              why: "We want the model analysing the conversation, not participating in it. Replayed as real turns it reliably answers instead of rewriting",
            },
          },
          {
            id: "identifiers",
            cells: {
              rule: "The prompt protects identifiers explicitly",
              why: "A rewriter that helpfully expands ERR_TIMEOUT_502 into 'timeout error' destroys the exact-match signal the keyword leg exists for. Pinned by a test",
            },
          },
        ]}
      />

      <p>
        The validator rejects empty output, output over 400 characters, output that grew more than
        6x <em>and</em> is long in absolute terms, multi-paragraph output, and text opening with a
        refusal or &ldquo;Sure, here is&rdquo;. On any rejection the raw query is used and the reason
        recorded — a degraded rewrite gives worse retrieval, whereas a raised exception gives no
        answer at all.
      </p>

      <H2 id="prompt">The generation prompt</H2>
      <p>
        Closed-book: the model sees the retrieved chunks and nothing else, with a numbered context
        block, a few-shot example, and a small set of rules.
      </p>

      <CodeBlock
        language="text"
        filename="app/generation/prompts.py (rules, paraphrased)"
        code={`1. Answer ONLY from the numbered sources below. If they do not contain the
   answer, say the fixed abstention sentence and nothing else.
2. Every factual claim carries an inline [n] marker naming the source it came from.
3. Do not merge two sources into one claim without citing both.
4. If sources disagree, prefer the one with the newer version or effective date,
   AND say that they disagree.
5. Never invent an error code, a version number, or a limit.`}
      />

      <DataTable
        columns={[
          { key: "knob", header: "Setting", width: "w-[32%]" },
          { key: "value", header: "Value", numeric: true },
          { key: "why", header: "Why" },
        ]}
        rows={[
          {
            id: "temp",
            cells: {
              knob: <code>llm_temperature</code>,
              value: "0.1",
              why: "Factual answers want 0.0–0.2. Not 0.0, because open models repeat themselves there",
            },
          },
          {
            id: "history",
            cells: {
              knob: <code>query_rewrite_history_turns</code>,
              value: "6",
              why: "Three exchanges. More drags stale entities from an earlier, unrelated problem into the query — the subtler of the two failures",
            },
          },
          {
            id: "abstention",
            cells: {
              knob: <code>abstention_message</code>,
              value: "fixed string",
              why: "The prompt, the detector that notices the model abstained, and the eval assertions must all agree on the exact sentence",
            },
          },
        ]}
      />

      <Callout kind="note" title="Conversation history is text only — never the earlier turns' sources">
        <p>
          Re-injecting earlier chunks would let the model answer turn three from turn one&apos;s
          context, and its citation markers would then point at sources absent from the current
          numbering — which post-hoc validation would correctly flag as fabrication. The prompt
          builder and the frontend&apos;s history helper follow the same rule, on both sides of the
          wire.
        </p>
      </Callout>

      <H2 id="validation">Citation validation</H2>
      <p>
        After the answer exists, it is split into sentence-level claims. Each claim is embedded with
        the same local encoder retrieval uses and compared against the chunks it cited. Threshold
        0.50. All claims and all cited chunks go into <strong>one batched embedding call</strong>,
        so validation latency does not scale with answer length — otherwise a more helpful answer
        would be a slower one, which is a perverse incentive.
      </p>

      <DataTable
        columns={[
          { key: "option", header: "Option", width: "w-[26%]" },
          { key: "verdict", header: "Verdict" },
        ]}
        rows={[
          {
            id: "similarity",
            cells: {
              option: "Embedding similarity",
              verdict:
                "Free, local, deterministic, ~30 ms. Runs on EVERY answer, which is the property that matters — a check that runs always beats a better check that gets disabled for being slow",
            },
            highlight: true,
          },
          {
            id: "judge",
            cells: {
              option: "LLM-as-judge",
              verdict:
                "Much stronger — catches contradiction, not just topical drift. Costs a call per answer, adds seconds, burns the quota the evaluation needs, and introduces a second model whose failures correlate with the generator's",
            },
          },
          {
            id: "nli",
            cells: {
              option: "An entailment model",
              verdict:
                "The technically right answer, and another ~1.4 GB model on a CPU already spending seconds on reranking. The latency would land on every answer",
            },
          },
        ]}
      />

      <Callout kind="caution" title="The hole, stated plainly">
        <p>
          Similarity catches &ldquo;this citation is unrelated&rdquo;. It cannot catch{" "}
          <strong>&ldquo;this citation says the opposite&rdquo;</strong>. <em>Retries cap at 3</em>{" "}
          and <em>retries cap at 5</em> are highly similar, because they are about the same thing —
          and that is precisely the stale-data failure this corpus plants. It is mitigated only
          partially, by the prompt&apos;s conflict rule and by the contested flag being surfaced in
          the context block and in the UI.
        </p>
        <p>
          The limitation is kept visible by naming: every identifier in the module says{" "}
          <code>similarity</code>, never <code>entailment</code> — the field on the claim, the
          config key, the threshold. A hole documented once in a docstring is a hole nobody
          remembers; a hole named at every call site is one you cannot forget.
        </p>
      </Callout>

      <H3 id="both-sides">A claim citing two sources needs only one to support it</H3>
      <p>
        Because rule 4 of the prompt explicitly asks the model to cite <em>both sides</em> of a
        conflict. Requiring every cited source to support the claim would punish the exact behaviour
        that was requested.
      </p>

      <H2 id="what-surfaces">What the interface does with the result</H2>
      <DataTable
        columns={[
          { key: "signal", header: "Signal", width: "w-[26%]" },
          { key: "ui", header: "How it appears" },
        ]}
        rows={[
          {
            id: "supported",
            cells: {
              signal: "Claim supported",
              ui: "Emerald verdict inside the expanded source, with the similarity",
            },
          },
          {
            id: "weak",
            cells: {
              signal: "Claim unsupported",
              ui: "Rose verdict, and a count in the panel header",
            },
          },
          {
            id: "invalid",
            cells: {
              signal: "Marker pointing at a source that was never offered",
              ui: "Rendered in rose in the answer text and listed as fabrication — flagged, not suppressed. The answer may still be correct, and hiding the discrepancy would be its own failure",
            },
            highlight: true,
          },
          {
            id: "unused",
            cells: {
              signal: "Source retrieved but never cited",
              ui: "Dimmed rather than hidden — in aggregate it is a retrieval-precision signal",
            },
          },
          {
            id: "contested",
            cells: {
              signal: "Chunk contested by a newer entry",
              ui: "Amber 'superseded in part' badge, computed at ingestion time rather than guessed in the browser",
            },
          },
        ]}
      />

      <p>
        <Link href="/docs/caching">
          What happens to the finished answer — and the one kind that is never cached →
        </Link>
      </p>
    </DocPage>
  );
}
