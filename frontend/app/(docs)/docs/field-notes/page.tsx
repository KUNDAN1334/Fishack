import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import Callout from "@/components/docs/Callout";
import DocPage from "@/components/docs/DocPage";
import { H2 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/field-notes")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/**
 * Seven bugs, each as expected → observed → root cause.
 *
 * The three-column structure is the point: a bug report says what broke, and
 * what is worth writing down is the GAP between what you expected and what
 * actually happened. Every one of these had a green test suite the whole time.
 */

interface Note {
  n: string;
  id: string;
  title: string;
  expected: ReactNode;
  observed: ReactNode;
  cause: ReactNode;
  lesson: ReactNode;
}

const NOTES: Note[] = [
  {
    n: "01",
    id: "tsquery",
    title: "Keyword search returned zero rows, and nothing complained",
    expected: (
      <>
        A realistic query like <em>&ldquo;webhook retry limit ERR_TIMEOUT_502&rdquo;</em> would
        match several chunks on the keyword leg and contribute them to fusion.
      </>
    ),
    observed: (
      <>
        Zero rows. Rank fusion silently degenerated to vector-only, and &ldquo;hybrid
        retrieval&rdquo; became a claim in a README rather than something that happened. No error,
        no warning, and the arm you would have blamed is the one still working.
      </>
    ),
    cause: (
      <>
        Every convenient Postgres helper joins terms with <code>AND</code>. That is boolean
        retrieval: a document must contain <em>every</em> term or it does not match. BM25 sums a
        per-term contribution, so partial matches must still score. No single chunk held all six
        lexemes — the docs page explains retry behaviour and names the error code, while the
        changelog entry is the one that says &ldquo;limit&rdquo;.
      </>
    ),
    lesson: (
      <>
        Fixing it by OR-ing everything then broke exact identifiers, because the parser splits{" "}
        <code>ERR_TIMEOUT_502</code> into three lexemes and any chunk containing <code>err</code>{" "}
        matched. The right answer distinguishes <code>&amp;</code> (concepts the user typed → OR)
        from <code>&lt;-&gt;</code> (one identifier held together → leave it alone). Three versions
        of one line, and only the second bug was findable by tests — the third needed looking at
        ranked output for a real query, which is what the playground is for.
      </>
    ),
  },
  {
    n: "02",
    id: "wrong-list",
    title: "The eval scored the wrong list, and made a working feature look useless",
    expected: (
      <>
        The <code>hybrid</code> and <code>hybrid+rerank</code> arms would produce visibly different
        scorecards, since the second one spends 1.4 seconds per query on a cross-encoder.
      </>
    ),
    observed: <>Byte-identical scorecards. The reranker appeared to do nothing at all.</>,
    cause: (
      <>
        The evaluation was scoring <code>candidates</code> — the <em>pre-rerank</em> list — because
        reranking returns a new list into <code>results</code> rather than re-sorting in place. Both
        arms had identical candidates, so both scored identically.
      </>
    ),
    lesson: (
      <>
        The obvious conclusion from that scorecard would have been <em>delete the reranker</em>.
        Once fixed it was worth +12% MRR overall and +33% on normal questions. A measurement that
        confidently reports &ldquo;no difference&rdquo; is not neutral — it actively argues for
        removing the thing it failed to measure.
      </>
    ),
  },
  {
    n: "03",
    id: "control",
    title: "A test that guards against fake passes, which itself passed fakely",
    expected: (
      <>
        The tenant-isolation test plants a secret in tenant B and asserts tenant A never sees it,
        with a <em>control</em> proving the secret is findable without the filter — so the test
        cannot pass on an empty index.
      </>
    ),
    observed: <>Green, and proving nothing.</>,
    cause: (
      <>
        The control counted text-search matches across the <em>whole</em> chunks table. The real
        two-tenant corpus satisfied it easily, while the synthetic test tenants matched nothing at
        all. The control vouched for a corpus that was not the one under test.
      </>
    ),
    lesson: (
      <>
        A control must be scoped as tightly as the thing it vouches for. It now asserts that{" "}
        <em>both</em> test tenants are reachable by the query. This is the most uncomfortable entry
        here, because the control existed <em>specifically</em> to prevent a vacuous pass, and
        vacuously passed.
      </>
    ),
  },
  {
    n: "04",
    id: "threshold",
    title: "A threshold nobody measured was wrong by 4x, in the direction that hid the feature",
    expected: (
      <>
        A conditional-rerank margin of <span className="figure">0.30</span> would skip the
        cross-encoder on unambiguous queries and save meaningful latency.
      </>
    ),
    observed: (
      <>
        It never fired. Real margins came out at <span className="figure">0.055–0.076</span>, and
        the arithmetic caps the achievable value at <span className="figure">0.062</span>.
      </>
    ),
    cause: (
      <>
        When every top-5 candidate is found by both legs — typical on this corpus — the fused scores
        are <code>2/(k+1) … 2/(k+5)</code>, a shape with a hard ceiling. So the margin was never
        measuring &ldquo;how confident is the top result&rdquo;. It measures{" "}
        <strong>&ldquo;was the top five unanimous&rdquo;</strong>, which is nearly binary.
      </>
    ),
    lesson: (
      <>
        The number sounded defensible and sat in a config file with a comment explaining its
        reasoning. That is the whole problem: a value that <em>looks</em> tuned and does nothing is
        worse than an obvious placeholder, because it silently makes a comparison show no difference
        and invites the conclusion that the feature does not matter. Moved to 0.10, where it{" "}
        <em>still</em> never fires — so it is documented as implemented and unproven rather than as
        a working optimisation.
      </>
    ),
  },
  {
    n: "05",
    id: "comparisons",
    title: "The same mistake, three times, in three places",
    expected: <>Three separate scorecards, each comparing two things.</>,
    observed: (
      <>
        Three confident numbers, none of which compared what it claimed to. The scorecard averaged
        three retrieval strategies into one row. The evaluation compared pre- and post-rerank lists
        as if they were the same list. The chunking experiment scored 8 cases in one arm and 41 in
        the other, and printed a delta anyway.
      </>
    ),
    cause: (
      <>
        All three are the same failure: <strong>a comparison that was not comparing the same
        things</strong>, presented as a confident number. Each one individually looked like an
        isolated slip.
      </>
    ),
    lesson: (
      <>
        The fix was not more care — care had already been applied three times. It was a{" "}
        <em>guard at each comparison point</em> that checks validity before formatting: same arm,
        same list, same case count, or refuse to print a delta. When the same mistake appears three
        times, it is a missing mechanism, not three lapses.
      </>
    ),
  },
  {
    n: "06",
    id: "semantic-cache",
    title: "A semantic cache is the most dangerous component in a RAG system",
    expected: (
      <>
        A 0.95 similarity threshold is conservative enough that a semantic cache hit means
        essentially the same question.
      </>
    ),
    observed: (
      <>
        <code>ERR_TIMEOUT_502</code> and <code>ERR_TIMEOUT_504</code> embed <em>above</em> 0.95 —
        they genuinely mean nearly the same thing — and have opposite correct answers.
      </>
    ),
    cause: (
      <>
        This is precisely the weakness hybrid retrieval exists to fix. Except the semantic cache is{" "}
        <strong>pure vector similarity</strong>: no keyword leg, no reranker, no confidence gate. It
        inherits the weakness with none of the mitigations that make it tolerable in retrieval.
      </>
    ),
    lesson: (
      <>
        Identifier-bearing queries now skip the semantic cache entirely, on write as well as read,
        so weakening the read-side guard later cannot detonate a stored landmine. And abstentions
        are never cached: &ldquo;I don&apos;t know&rdquo; is a fact about the corpus at one moment,
        and caching it makes the system refuse documentation it now has.
      </>
    ),
  },
  {
    n: "07",
    id: "instrumentation",
    title: "Instrumentation that lies precisely when the feature works",
    expected: (
      <>
        Replaying the cached answer&apos;s original cost onto a cache hit keeps the accounting
        honest.
      </>
    ),
    observed: (
      <>
        Cost-per-query would <em>rise</em> as the cache hit rate improved. The dashboard would show
        the system getting more expensive exactly as it got cheaper.
      </>
    ),
    cause: (
      <>
        A cache hit is free. Attributing the original request&apos;s spend to it describes a request
        that never happened — and it does so on the one metric caching exists to move.
      </>
    ),
    lesson: (
      <>
        A cache hit now records zero tokens and zero cost. Provider and model <em>are</em> kept,
        because &ldquo;which model wrote this cached answer?&rdquo; is a real debugging question.
        Instrumentation that inverts its signal is worse than none, because it is believed.
      </>
    ),
  },
];

export default function FieldNotesPage() {
  return (
    <DocPage
      href="/docs/field-notes"
      eyebrow="Reference"
      title="Field notes"
      lead="Seven bugs, each as expected → observed → root cause. The common thread is that none of them crashed: the full test suite was green the entire time, and every one of them would have shipped."
    >
      <Callout kind="caution" title="The dangerous failures are the silent ones">
        <p>
          Every entry here was found by looking at output, not by a failing test. Four of them were
          found by the evaluation harness, one by a debugging playground, and one by a test that was
          itself passing for the wrong reason. That distribution is the argument for building the
          harness before it feels necessary.
        </p>
      </Callout>

      <div className="!mt-8 space-y-8">
        {NOTES.map((note) => (
          <section
            key={note.id}
            id={note.id}
            className="scroll-mt-24 overflow-hidden rounded-xl border border-line bg-surface"
          >
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line bg-surface-sunken px-4 py-3">
              <span className="figure text-xs font-semibold text-ocean-600">{note.n}</span>
              <h2 className="text-sm font-semibold text-slate-900">{note.title}</h2>
            </header>

            <div className="divide-y divide-line">
              {(
                [
                  ["What I expected", note.expected],
                  ["What happened", note.observed],
                  ["Why", note.cause],
                ] as const
              ).map(([label, body]) => (
                <div key={label} className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-6">
                  <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
                    {label}
                  </p>
                  <div className="text-sm leading-relaxed text-slate-700">{body}</div>
                </div>
              ))}
              <div className="bg-ocean-50/40 px-4 py-3.5">
                <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.1em] text-ocean-700">
                  What it changed
                </p>
                <div className="text-sm leading-relaxed text-slate-700">{note.lesson}</div>
              </div>
            </div>
          </section>
        ))}
      </div>

      <H2 id="pattern">The pattern across all seven</H2>
      <p>
        Five of these are the same species: <strong>something reported a number, and the number was
        about the wrong thing</strong>. A keyword leg reporting no matches because it was asking a
        boolean question. An evaluation reporting no difference because it was scoring the list
        before the change. A control reporting &ldquo;findable&rdquo; about a different corpus. A
        threshold reporting a decision it could never make. A cost metric reporting spend on a
        request that never ran.
      </p>
      <p>
        None of them raised. All of them were confident. The defence that actually worked was not
        more tests — it was <em>looking at real output for a real query</em>, and building a harness
        whose job is to compare two things and refuse to print a number when they are not
        comparable.
      </p>

      <p>
        <Link href="/docs/limitations">
          What is still wrong, or unmeasured, or open →
        </Link>
      </p>
    </DocPage>
  );
}
