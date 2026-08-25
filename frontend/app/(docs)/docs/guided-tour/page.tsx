import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import DocPage from "@/components/docs/DocPage";
import { H2 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";
import { ArrowRight } from "@/components/ui/Icon";

const meta = findDoc("/docs/guided-tour")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/**
 * The guided tour.
 *
 * Written as a sequence of numbered cases rather than prose, because the ORDER
 * is the content: each query turns on a defence the previous one did not need,
 * and running them out of order makes several of them look like nothing is
 * happening. Someone who follows this page top to bottom has seen every claim
 * the product makes, in about three minutes.
 */

interface TourCase {
  n: string;
  query: string;
  proves: string;
  watch: React.ReactNode;
  why: React.ReactNode;
}

const CASES: TourCase[] = [
  {
    n: "01",
    query: "What is the webhook retry limit?",
    proves: "Conflicting sources, resolved and disclosed",
    watch: (
      <>
        The sources panel populates <em>before the first token of the answer</em>. One of the
        sources carries an amber <strong>superseded in part</strong> badge. The answer should
        prefer the newer figure and say that the two sources disagree.
      </>
    ),
    why: (
      <>
        This is a deliberately planted conflict. The product documentation says the retry limit is
        3; the v2.4 changelog entry says 5, and it declares the conflict rather than superseding
        the whole page — because the changelog contradicts one <em>fact</em> on that page, not the
        page. Archiving the doc would destroy correct information to fix one stale sentence, so the
        conflict is pushed to generation time on purpose, where the model must prefer the newest
        source <em>and</em> flag the discrepancy. In production nobody remembers to mark the old
        doc; a system that only handles declared supersession handles the easy half.
      </>
    ),
  },
  {
    n: "02",
    query: "What causes ERR_TIMEOUT_502?",
    proves: "Exact identifiers, where the keyword leg earns its place",
    watch: (
      <>
        A ticket source, and an answer naming the specific cause. Compare it with{" "}
        <code>make playground</code> on the same query: the vector leg alone ranks a{" "}
        <em>different</em> error code&apos;s ticket highly, because embeddings encode meaning and
        two error codes mean nearly the same thing.
      </>
    ),
    why: (
      <>
        Postgres&apos; text-search parser splits <code>ERR_TIMEOUT_502</code> into three lexemes,
        so a naive OR over them matches any chunk containing <code>err</code>. The keyword leg
        keeps the identifier together with a followed-by operator while OR-ing the terms the user
        actually typed as separate ideas. That one line took three versions to get right, and{" "}
        <Link href="/docs/field-notes">field note 1</Link> is the whole story.
      </>
    ),
  },
  {
    n: "03",
    query: "What is the capital of France?",
    proves: "Abstention, at zero cost",
    watch: (
      <>
        An amber escalation banner — <em>not</em> red — with a ticket id, and a timing strip
        showing <strong>no generation stage at all</strong>. The model was never called.
      </>
    ),
    why: (
      <>
        The confidence gate sits <em>before</em> generation, so a question the corpus cannot answer
        costs nothing but a retrieval round trip. The banner is amber because abstaining is the
        system working correctly; red would train a user to read correct behaviour as a fault, and
        that is the single most important colour decision in the application. The escalation row
        carries the conversation and the top ten sources with their scores, because &ldquo;the
        right chunk was at rank 7&rdquo; and &ldquo;the right chunk was never retrieved&rdquo; are
        different bugs with different fixes.
      </>
    ),
  },
  {
    n: "04",
    query: "Ask the same question a second time",
    proves: "The cache, and instrumentation that does not lie",
    watch: (
      <>
        A <strong>cached</strong> badge, and total time dropping to roughly 10 ms. The cost figure
        for this request reads <span className="figure">$0.000000</span>.
      </>
    ),
    why: (
      <>
        A cache hit records zero tokens and zero cost. Replaying the original answer&apos;s spend
        would make cost-per-query <em>rise</em> as caching improved — the dashboard would show the
        system getting more expensive exactly as it got cheaper, on the one metric caching exists
        to move. The provider and model <em>are</em> replayed, because &ldquo;which model wrote this
        cached answer?&rdquo; is a real debugging question.
      </>
    ),
  },
  {
    n: "05",
    query: "Switch tenant, then ask 02 again",
    proves: "Isolation, and that it is structural",
    watch: (
      <>
        The conversation clears, and the menu says so before you click. The same question now
        returns different private documents — or abstains, if that tenant&apos;s corpus does not
        cover it.
      </>
    ),
    why: (
      <>
        Switching clears history because carrying it across would feed one tenant&apos;s answers
        into another&apos;s prompt as context. That is not a chunk leak, but it is a leak, and
        doing it silently would be the more convenient design and the less honest one. Underneath,
        every database read goes through a scope that owns the <code>FROM</code> clause; a row that
        surfaces outside its tenant raises rather than being quietly filtered away.{" "}
        <Link href="/docs/tenant-isolation">The isolation page</Link> has the four layers.
      </>
    ),
  },
];

export default function GuidedTourPage() {
  return (
    <DocPage
      href="/docs/guided-tour"
      eyebrow="Start here"
      title="Guided tour"
      lead="Five queries, in this order. Each one turns on a defence the previous one did not need, so running them out of sequence makes several of them look like nothing is happening. About three minutes end to end."
    >
      <Callout kind="note" title="Run these in the assistant">
        <p>
          Open <Link href="/try">the assistant</Link> with tenant <code>acme</code> selected. Keep
          the operations dashboard in a second tab — cases 3 and 4 move numbers on it while you
          watch.
        </p>
      </Callout>

      <H2 id="cases">The five cases</H2>

      <div className="!mt-6 space-y-4">
        {CASES.map((item) => (
          <section
            key={item.n}
            className="overflow-hidden rounded-xl border border-line bg-surface"
          >
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line bg-surface-sunken px-4 py-3">
              <span className="figure text-xs font-semibold text-ocean-600">{item.n}</span>
              <p className="text-sm font-semibold text-slate-900">{item.query}</p>
              <span className="ml-auto text-xs text-slate-500">{item.proves}</span>
            </header>
            <div className="grid gap-x-8 gap-y-4 px-4 py-4 sm:grid-cols-2">
              <div>
                <p className="mb-1.5 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
                  What to watch
                </p>
                <p className="text-sm leading-relaxed text-slate-700">{item.watch}</p>
              </div>
              <div>
                <p className="mb-1.5 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
                  Why it works that way
                </p>
                <p className="text-sm leading-relaxed text-slate-600">{item.why}</p>
              </div>
            </div>
          </section>
        ))}
      </div>

      <H2 id="closer">The closer</H2>
      <p>
        The most persuasive part of this project is not in the UI at all. Run{" "}
        <code>make eval-retrieval</code>: under a minute, no LLM calls, and it prints a scorecard
        comparing five retrieval strategies over the 65-case golden set.
      </p>
      <p>
        The scorecard says <strong>hybrid retrieval lost to vector-only on this corpus</strong> —
        which contradicts the design document that specified hybrid retrieval, and is the most
        useful thing the harness produced. A system that can only confirm its own design is not
        being measured.{" "}
        <Link href="/docs/results">
          The results page has every number and the caveat that bounds it
        </Link>
        .
      </p>

      <div className="!mt-8 flex flex-wrap gap-3">
        <Link
          href="/try"
          className="group inline-flex items-center gap-2 rounded-md bg-ocean-600 px-4 py-2.5
                     text-sm font-medium text-white no-underline transition-colors hover:bg-ocean-700"
        >
          Open the assistant
          <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
        </Link>
        <Link
          href="/docs/query-path"
          className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-4 py-2.5
                     text-sm font-medium text-slate-700 no-underline transition-colors hover:bg-slate-50"
        >
          See what happens inside a request
        </Link>
      </div>
    </DocPage>
  );
}
