import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Steps from "@/components/docs/Steps";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/ingestion")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function IngestionPage() {
  return (
    <DocPage
      href="/docs/ingestion"
      eyebrow="Architecture"
      title="Ingestion and chunking"
      lead="Three source types, three chunking strategies, and a second pass that runs only after every document has landed. Chunking is the highest-leverage decision in the whole system: it beat every retrieval-side change that was measured against it."
    >
      <H2 id="pipeline">The pipeline</H2>
      <Steps
        steps={[
          {
            title: "Load",
            aside: "3 loaders",
            body: (
              <>
                Product docs are Markdown with YAML frontmatter; the changelog and the ticket
                archive are JSONL, one record per line. Each loader emits the same{" "}
                <code>ParsedDocument</code>, so nothing downstream branches on where a document came
                from except the chunker selection.
              </>
            ),
          },
          {
            title: "Deduplicate by content hash",
            aside: "idempotent",
            body: (
              <>
                A document whose <code>content_hash</code> already exists is skipped entirely. This
                is what makes re-running ingestion nearly free, and it is why the quickstart can
                tell you to just run it again if you are not sure whether it finished.
              </>
            ),
          },
          {
            title: "Chunk, by source type",
            aside: "outside the transaction",
            body: (
              <>
                Three strategies, described below. Chunking is CPU work and embedding is
                model work, so both happen <em>before</em> the transaction opens — holding a
                database transaction across two minutes of embedding would be the easiest way to
                turn a slow ingest into a lock-contention incident.
              </>
            ),
          },
          {
            title: "Embed, through a cache",
            aside: "sha256(model + text)",
            body: (
              <>
                Only cache misses reach the model, in batches of 32. The cache is keyed on the model
                name as well as the text, because embeddings from different models live in different
                spaces and are never comparable — a key without the model name would silently mix
                two vector spaces in one index.
              </>
            ),
          },
          {
            title: "Insert transactionally",
            aside: "document + chunks",
            body: (
              <>
                The document row and all of its chunks land in one transaction, and any previous
                version of that document is archived — marked <code>is_current = false</code>, never
                deleted. Chunk ids for the outgoing version are collected <em>before</em> the delete,
                because afterwards there is no way to know which cached answers went stale.
              </>
            ),
          },
          {
            title: "Second pass, after every document",
            aside: "supersede + tag",
            body: (
              <>
                Changelog entries can retire a document or contest one fact on it. Both are applied
                only once the whole corpus is in.
              </>
            ),
          },
          {
            title: "Invalidate the cache, after the commit",
            aside: "reverse index",
            body: (
              <>
                Every cached answer records which chunks it was built from, so re-ingesting a
                document deletes precisely the answers that depended on it. Running this{" "}
                <em>after</em> the commit is deliberate: inside the transaction a rollback would
                clear the cache for content that still exists, which costs a few extra LLM calls.
                The reverse — new content committed while stale answers survive — is much worse.
              </>
            ),
          },
        ]}
      />

      <Callout kind="note" title="Why the second pass is a separate pass">
        <p>
          A changelog entry may supersede a document that has not been ingested yet in the same run.
          Handling supersession inline would make the result depend on file ordering — the corpus
          would be correct or incorrect depending on which file the loader happened to read first,
          and it would be correct most of the time.
        </p>
      </Callout>

      <H2 id="chunkers">Three chunking strategies</H2>
      <p>
        Each source type has a natural unit, and a fixed-size window destroys all three of them. A
        docs page has sections; a changelog has entries; a ticket has a question and its resolution,
        which are worthless apart.
      </p>

      <DataTable
        columns={[
          { key: "source", header: "Source", width: "w-[18%]" },
          { key: "unit", header: "Unit" },
          { key: "size", header: "Target size", numeric: true },
          { key: "special", header: "Special handling" },
        ]}
        rows={[
          {
            id: "docs",
            cells: {
              source: "Product docs",
              unit: "One heading section",
              size: "300–500 tok",
              special:
                "Heading path prepended into the content; 15% overlap; tables and code fences never split; stub sections merged with siblings",
            },
          },
          {
            id: "changelog",
            cells: {
              source: "Changelog",
              unit: "One entry",
              size: "50–200 tok",
              special:
                "Version and date appear both in the text — for the keyword leg and the conflict rule — and in metadata, for recency",
            },
          },
          {
            id: "tickets",
            cells: {
              source: "Support tickets",
              unit: "One question–resolution pair",
              size: "≤ 500 tok",
              special:
                "Error code repeated in the header line; a long ticket splits at the question/answer seam and each half is re-labelled",
            },
          },
        ]}
      />

      <H3 id="heading-prefix">The heading path goes into the content, not just the metadata</H3>
      <p>
        A docs chunk&apos;s stored content begins with its position in the document hierarchy:
      </p>
      <CodeBlock
        language="text"
        code={`content = "Billing > Invoices > Proration\\n\\n<section body>"`}
      />
      <p>
        This is decided at ingestion time and is expensive to change later, because both the
        keyword index and the embedding are computed from <code>content</code> — reversing it means
        re-chunking and re-embedding everything.
      </p>
      <p>
        The reason is that a section&apos;s body frequently never repeats its own topic words.
        &ldquo;Proration is calculated daily…&rdquo; sitting under the heading{" "}
        <em>Webhooks &gt; Retry Logic</em> would be unfindable for the query &ldquo;webhook
        retry&rdquo;. Prepending puts those words into <strong>both</strong> the text-search vector
        and the embedding at once, and gives the generator the chunk&apos;s position in the document
        without extra prompt assembly. The clean path is also stored in its own column, for display
        and metadata filtering.
      </p>

      <H3 id="tokens">Token budgets are measured with the model&apos;s own tokenizer</H3>
      <p>
        A chunk that is &ldquo;450 tokens&rdquo; by word count can be 700 real tokens. It gets
        stored whole, embedded <em>truncated</em> at the model&apos;s 512 limit, and retrieval
        quietly degrades with nothing in any log. Silent truncation is the worst class of ingestion
        bug because everything appears to work.
      </p>
      <p>
        So budgets are measured with the embedding model&apos;s HuggingFace tokenizer. And because
        per-unit counts are <em>not additive</em> — joining adds separators, and subword merging
        behaves differently across a boundary — the docs chunker measures the actual joined
        candidate string and runs a final enforcement pass over finished chunks. Summing the parts
        underestimates, which is precisely how a chunk sneaks past the cap.
      </p>

      <Callout kind="result" title="Chunking beat every retrieval-side change measured against it">
        <p>
          The same corpus ingested twice — once per-source, once with fixed 1,600-character windows
          — under shadow tenants and scored identically. Overall recall@5 went from 0.591 to 0.858.
          Naive chunking loses <strong>45% of multi-turn answers entirely</strong>: not ranked
          lower, absent from the top 20.{" "}
          <Link href="/docs/results#chunking">The full comparison, with its caveat →</Link>
        </p>
      </Callout>

      <H2 id="versioning">Versioning and planted conflicts</H2>
      <p>
        Stale data is the failure mode this system exists to handle, so the corpus contains{" "}
        <strong>two kinds</strong> of it. A corpus with only one kind can only demonstrate one
        defence.
      </p>

      <DataTable
        columns={[
          { key: "kind", header: "Kind", width: "w-[20%]" },
          { key: "mechanism", header: "Mechanism" },
          { key: "behaviour", header: "Ingestion behaviour" },
          { key: "tests", header: "Which defence it tests" },
        ]}
        rows={[
          {
            id: "superseded",
            cells: {
              kind: "Superseded",
              mechanism: <code>supersedes: &lt;slug&gt;</code>,
              behaviour: "The document and its chunks become is_current = false",
              tests: "Ingestion-time metadata discipline",
            },
          },
          {
            id: "conflict",
            cells: {
              kind: "Unmarked conflict",
              mechanism: <code>conflicts_with: &lt;slug&gt;</code>,
              behaviour: "Both stay live; the doc's chunks are tagged conflicts_with_entry",
              tests: "The generation-time conflict rule, and the amber badge in the UI",
            },
            highlight: true,
          },
        ]}
      />

      <H3 id="why-not-archive">Why the contested document is not archived too</H3>
      <p>
        Because the changelog contradicts one <em>fact</em> on that page — &ldquo;the retry limit is
        now 5&rdquo; — not the page. The rest of &ldquo;Webhooks Overview&rdquo; is still correct,
        and archiving it would destroy good information to fix one stale sentence.
      </p>
      <p>
        So the conflict is deliberately pushed to generation time, where the model must prefer the
        newest source <strong>and</strong> flag the discrepancy, and where the interface can show
        the contested source with an amber badge. This is also the realistic case: in production
        nobody remembers to mark the old document, and a system that only handles declared
        supersession handles the easy half of the problem.
      </p>

      <H2 id="corpus">How the corpus itself is built</H2>
      <p>
        The evaluation harness needs to map queries to <em>known-correct</em> sources, which is only
        possible if the corpus contents are known with certainty. So the corpus is generated
        hybrid: every document, version, date, error code and planted conflict is{" "}
        <strong>declared in Python</strong>, and only the body prose is written by a model, keyed by
        prompt hash into a committed disk cache with a deterministic template fallback.
      </p>

      <DataTable
        columns={[
          { key: "approach", header: "Approach", width: "w-[24%]" },
          { key: "problem", header: "Why it was rejected" },
        ]}
        rows={[
          {
            id: "templates",
            cells: {
              approach: "Fully templated",
              problem:
                "Perfectly reproducible, and the prose is formulaic in a way that makes retrieval unrealistically easy — every chunk reads the same, so lexical overlap with queries is artificial",
            },
          },
          {
            id: "llm",
            cells: {
              approach: "Fully LLM-generated",
              problem:
                "Realistic, and the facts drift. A model asked for sixty doc pages invents its own error codes and contradicts itself, so ground truth becomes unverifiable and regeneration silently changes it",
            },
          },
          {
            id: "hybrid",
            cells: {
              approach: "Hybrid — declared facts, generated prose",
              problem:
                "Facts the evaluation depends on are never generated. Prose, which only needs to be plausible, is. The cache makes reruns byte-identical, and the fallback means a fresh clone works with no API key at all",
            },
            highlight: true,
          },
        ]}
        caption="A guardrail warns — rather than fails — when a required literal from the brief does not survive into the generated text. A hundred-document run should not abort, but you must know before building a golden set on it."
      />

      <Callout kind="caveat">
        <p>
          Synthetic generation makes ground truth reliable and makes <em>difficulty</em>{" "}
          unrepresentative. This corpus is smooth, semantically coherent AI prose, which flatters
          vector search and understates what a keyword leg is worth on real documentation full of
          internal jargon and codenames. Every retrieval result on this site is bounded by that.
        </p>
      </Callout>
    </DocPage>
  );
}
