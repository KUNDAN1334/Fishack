import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/caching")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function CachingPage() {
  return (
    <DocPage
      href="/docs/caching"
      eyebrow="Architecture"
      title="Caching"
      lead="A semantic cache is the most dangerous component in a RAG system: its failure is silent, durable, and looks exactly like a hallucination. This one ships with two hard guardrails, an active invalidation path, and a rule about what it is never allowed to store."
    >
      <H2 id="two-caches">Two caches, cheapest and safest first</H2>
      <p>
        An exact lookup is an O(1) Redis <code>GET</code> and <strong>cannot be wrong</strong>. A
        semantic lookup needs an embedding and a similarity scan and <em>can</em> be wrong. So the
        cheap safe one runs first, and the fuzzy one only on a miss.
      </p>

      <DataTable
        columns={[
          { key: "layer", header: "Layer", width: "w-[20%]" },
          { key: "key", header: "Key" },
          { key: "cost", header: "Cost", numeric: true },
          { key: "risk", header: "Failure mode" },
        ]}
        rows={[
          {
            id: "exact",
            cells: {
              layer: "Exact",
              key: "tenant + the rewritten query, hashed",
              cost: "~1 ms",
              risk: "None — it is the same question",
            },
          },
          {
            id: "semantic",
            cells: {
              layer: "Semantic",
              key: "cosine similarity ≥ 0.95 against recent keys",
              cost: "~15 ms",
              risk: "Serves an answer written for a DIFFERENT question",
            },
            highlight: true,
          },
        ]}
      />

      <H2 id="key">The cache is keyed on the rewritten query, and sits after rewriting</H2>
      <p>
        Both rewriting and the cache want to be first. Rewriting wins, and the reason is a
        correctness bug rather than a preference.
      </p>
      <p>
        &ldquo;What about the backoff?&rdquo; means something different in a conversation about
        webhooks than in one about rate limits — the same four words, two correct answers. Keying on
        the raw query would serve one conversation&apos;s answer into another, which is a
        correctness failure that looks exactly like a model hallucination and would be debugged as
        one.
      </p>
      <p>
        The rewritten query is <em>standalone by construction</em> — that is the entire property
        rewriting produces, and it is precisely what a cache key needs.
      </p>

      <Callout kind="note" title="What that costs">
        <p>
          A cache hit on a follow-up still pays for one rewrite call, so the &ldquo;free&rdquo; path
          is not free on multi-turn conversations. First-turn queries skip rewriting entirely and
          are the majority, so the common case is unaffected. Caching on the raw key <em>as well</em>{" "}
          would double the hit rate on repeated follow-ups and reintroduce the collision — the raw
          key is unsafe no matter what sits beside it.
        </p>
      </Callout>

      <H2 id="guardrails">Two guardrails make a 0.95 threshold survivable</H2>

      <H3 id="identifiers">Guardrail 1 — identifier-bearing queries skip the semantic cache</H3>
      <p>Embeddings encode meaning, and two error codes <em>mean</em> nearly the same thing.</p>
      <CodeBlock
        language="text"
        code={`"what causes ERR_TIMEOUT_502?"
"what causes ERR_TIMEOUT_504?"

   -> embed far above 0.95 similarity
   -> have completely different correct answers`}
      />
      <p>
        This is the same weakness that justified a hybrid retrieval design in the first place. But
        the semantic cache is <strong>pure vector similarity</strong> — no keyword leg, no
        reranker, no confidence gate. It inherits the weakness with none of the mitigations that
        make it tolerable in retrieval.
      </p>
      <p>
        So a broad identifier detector — error codes, version strings, HTTP status codes, ticket ids,
        endpoint paths — disables the fuzzy path for those queries. Deliberately broad: a false
        positive costs one cache miss, a false negative serves the wrong error code&apos;s answer.
        It is applied on <strong>write</strong> as well as read, so weakening the read-side guard
        later cannot detonate a stored landmine.
      </p>
      <p>The exact cache still serves these queries. Only the fuzzy path, where the danger is, is off.</p>

      <H3 id="abstentions">Guardrail 2 — abstentions are never cached</H3>
      <p>
        &ldquo;I don&apos;t have enough information&rdquo; is a statement about the corpus{" "}
        <em>at one moment</em>. Cache it and the refusal survives for an hour after someone adds the
        missing documentation: the system actively declines to use content it now has, and tells the
        user nothing exists.
      </p>
      <p>
        Ingestion-time versioning exists to stop serving stale information. Caching a refusal would
        reintroduce staleness in its worst form — as a confident absence. The refusal lives in the
        store function, not at the call sites, so there is exactly one place that decides and a
        future caller cannot forget.
      </p>

      <Callout kind="caveat" title="0.95 is a design number, not a measured one">
        <p>
          The guardrails make it survivable; they do not validate it. The evaluation harness can now
          measure whether the semantic cache costs recall, and that run has not happened. Recorded
          as open rather than quietly assumed correct. Raising it to 0.98 would reduce but not
          remove the identifier problem — two error codes can exceed 0.98 — while cutting the hit
          rate enough to undermine the cost argument the cache exists for.
        </p>
      </Callout>

      <H2 id="invalidation">Active invalidation</H2>
      <p>
        Every cached answer records a <code>chunk_id → {"{"}cache keys{"}"}</code> mapping in Redis.
        Re-ingesting a document collects its chunk ids and deletes precisely the answers built on
        them.
      </p>

      <DataTable
        columns={[
          { key: "approach", header: "Approach", width: "w-[26%]" },
          { key: "verdict", header: "Verdict" },
        ]}
        rows={[
          {
            id: "reverse",
            cells: {
              approach: "Reverse index",
              verdict:
                "Precise. An answer built on five chunks dies if any one changes — conservative by design, because regenerating costs one LLM call and serving a stale answer costs trust",
            },
            highlight: true,
          },
          {
            id: "wipe",
            cells: {
              approach: "Wipe the tenant's cache on any change",
              verdict:
                "Simple and correct, and re-ingestion is routine — the hit rate would spend most of its life near zero, defeating the cost argument",
            },
          },
          {
            id: "ttl",
            cells: {
              approach: "TTL only",
              verdict:
                "Least code. Serves a stale answer for up to an hour after a correction ships, which is the exact failure this corpus plants conflicts to test",
            },
          },
        ]}
      />

      <H3 id="three-details">Three implementation details that are the actual decision</H3>
      <ul>
        <li>
          <strong>Chunk ids are collected before the delete.</strong> Afterwards they no longer
          exist, and the cache has no way to know which answers went stale.
        </li>
        <li>
          <strong>Archived chunks are included.</strong> An answer cached before a supersession was
          built on chunks now marked not-current — that answer is exactly the stale one to evict.
        </li>
        <li>
          <strong>Invalidation runs after the transaction commits.</strong> Inside it, a rollback
          would clear the cache for content that still exists, which costs a few extra LLM calls.
          The reverse — new content committed while stale answers survive — is much worse.
        </li>
      </ul>
      <p>
        The reverse index carries a TTL of twice the cache TTL, so a late invalidation still finds
        something to delete. A failed invalidation is the one cache error with a real cost, so it
        logs at warning level rather than debug — while still never failing an ingest that has
        already committed.
      </p>

      <H2 id="cost-reporting">A cache hit reports zero cost</H2>
      <p>
        The cached entry carries the original provider, model and spend. Only the first two are
        replayed onto the new response.
      </p>
      <Callout kind="caution" title="Reporting the original spend would invert the metric">
        <p>
          Cost-per-query would <em>rise</em> as caching improved. The dashboard would show the
          system getting more expensive exactly as it got cheaper, on the one metric caching exists
          to move. That is instrumentation lying precisely when the feature works, which is worse
          than no instrumentation because it is believed.
        </p>
      </Callout>
      <p>
        Provider and model <em>are</em> kept, because &ldquo;which model wrote this cached
        answer?&rdquo; is a real debugging question when a cached answer turns out to be bad. The
        same reasoning drives what the cache entry stores at all: no retrieval result — that is a
        second copy of the corpus — and no per-request timings, because a cache hit took 4 ms, not
        the original 3,200 ms.
      </p>
      <p>
        The event shape stays identical (<code>meta</code>, <code>delta</code>, <code>final</code>)
        so a client cannot tell the difference structurally. But the <code>delta</code> carries the
        whole answer at once: faking a typing animation for text already in hand would be adding
        latency to make a fast path look slow.
      </p>

      <H2 id="degradation">When Redis is unavailable</H2>
      <p>
        Every Redis call is wrapped, so a cache failure degrades to a miss rather than an error. The
        cache can also be disabled outright with one environment variable. This matters on a free
        tier: Upstash&apos;s command allowance is finite and the cache spends it on every request,
        so exhausting the quota has to be survivable rather than fatal.
      </p>

      <p>
        <Link href="/docs/operations">
          What the cache hit rate means on the dashboard, and when a change to it is a problem →
        </Link>
      </p>
    </DocPage>
  );
}
