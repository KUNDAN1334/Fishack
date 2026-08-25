import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Figure from "@/components/docs/Figure";
import RetrievalDiagram from "@/components/docs/diagrams/RetrievalDiagram";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/retrieval")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function RetrievalPage() {
  return (
    <DocPage
      href="/docs/retrieval"
      eyebrow="Architecture"
      title="Retrieval and ranking"
      lead="Two legs on incomparable score scales, merged by rank rather than by score, then optionally reranked by a cross-encoder that costs more than the entire latency budget. Every part of this was measured, and the measurement disagreed with the design."
    >
      <Figure caption="The keyword and vector legs run concurrently and neither writes a full query — both hand a fragment to the scope that owns the FROM clause. Fusion needs no hydration step because both legs return full rows.">
        <RetrievalDiagram />
      </Figure>

      <H2 id="keyword-leg">The keyword leg</H2>
      <p>
        BM25-style keyword matching is provided by Postgres full-text search: a generated{" "}
        <code>tsvector</code> column on <code>chunks</code> with a GIN index, ranked with{" "}
        <code>ts_rank_cd</code>.
      </p>
      <p>
        The alternative was a real BM25 engine. A Python BM25 library keeps its index in process
        memory, so it must be rebuilt on every restart and for every worker, and tenant filtering
        happens in Python <em>after</em> scoring — which is precisely the application-level
        isolation this system is built to avoid. Elasticsearch is real BM25 and a second datastore
        to keep consistent with Postgres, which is a large operational bill at this scale.
      </p>
      <p>
        One datastore for both legs means one tenant predicate enforced in SQL for both, one backup
        story, and index consistency guaranteed by the generated column.
      </p>

      <Callout kind="caveat" title="ts_rank_cd is not BM25">
        <p>
          It lacks BM25&apos;s document-length normalisation and corpus-level IDF saturation. For
          short-to-medium chunks of similar length — which is what the chunker targets — the ranking
          behaviour is close enough, and rank fusion consumes only <em>ranks</em>, which mutes the
          difference further. At scale, or with heterogeneous document lengths, this wants a real
          BM25 engine or ParadeDB&apos;s <code>pg_search</code>.
        </p>
      </Callout>

      <H3 id="tsquery">The query must OR its terms, and every convenient helper ANDs them</H3>
      <p>
        This shipped broken and is worth recording honestly, because the failure was silent in
        exactly the way this project is meant to guard against.
      </p>
      <CodeBlock
        language="sql"
        code={`websearch_to_tsquery('english', 'webhook retry limit')
  ->  'webhook' & 'retri' & 'limit'`}
      />
      <p>
        That is <strong>boolean retrieval</strong>: a document must contain every term or it does
        not match at all. BM25 does not work that way — it <em>sums</em> a per-term contribution
        over the terms a document does contain, so a document matching four of six query terms still
        scores, just lower. Ranked retrieval is inherently OR-ed; the ranking function decides what
        wins, not the matcher.
      </p>
      <p>
        The consequence was severe and quiet. The realistic query{" "}
        <code>&quot;webhook retry limit ERR_TIMEOUT_502&quot;</code> returned{" "}
        <strong>zero rows</strong>, because the docs page explains retry behaviour and names the
        error code while the changelog entry is the one that says &ldquo;limit&rdquo;. No single
        chunk held all six lexemes. The keyword leg contributed nothing, fusion degenerated to
        vector-only, and &ldquo;hybrid retrieval&rdquo; became a claim in a README rather than
        something that happened.
      </p>

      <H3 id="two-operators">Two operators, two meanings</H3>
      <p>
        The naive fix — OR everything — broke exact identifiers instead. Postgres&apos; default
        parser treats <code>_</code> as a separator, so <code>ERR_TIMEOUT_502</code> becomes three
        independent lexemes and a flat OR matches any chunk containing <code>err</code>. On the real
        corpus, a query for one error code pulled a completely different error code&apos;s ticket
        into the top five.
      </p>
      <p>
        The observation that resolves it is that <code>websearch_to_tsquery</code> already
        distinguishes the two cases:
      </p>
      <CodeBlock
        language="sql"
        code={`websearch_to_tsquery('english', 'ERR_TIMEOUT_502')
  ->  'err' <-> 'timeout' <-> '502'        -- followed-by: adjacency IS the point`}
      />

      <DataTable
        columns={[
          { key: "op", header: "Operator", width: "w-[16%]" },
          { key: "separates", header: "What it separates" },
          { key: "handling", header: "Correct handling" },
        ]}
        rows={[
          {
            id: "and",
            cells: {
              op: <code>&amp;</code>,
              separates: "Concepts the user typed as separate ideas",
              handling: "Rewrite to |  — this is ranked retrieval",
            },
          },
          {
            id: "phrase",
            cells: {
              op: <code>&lt;-&gt;</code>,
              separates: "One identifier, or a quoted phrase, that the tokenizer happened to split",
              handling: "Leave alone — adjacency is the signal",
            },
            highlight: true,
          },
        ]}
      />

      <CodeBlock
        language="sql"
        filename="app/retrieval/bm25.py"
        code={`SELECT NULLIF(replace(websearch_to_tsquery('english', $2)::text, ' & ', ' | '), '')::tsquery

-- 'webhook' & 'retri' & 'limit' & 'err' <-> 'timeout' <-> '502'
--     becomes
-- 'webhook' | 'retri' | 'limit' | ('err' <-> 'timeout' <-> '502')`}
      />
      <p>
        Operator precedence does the rest: <code>&lt;-&gt;</code> binds tighter than{" "}
        <code>&amp;</code>, which binds tighter than <code>|</code>, so the phrase group survives
        intact. A chunk mentioning only <code>err</code> no longer matches the identifier clause; a
        chunk about webhooks still matches on one concept. <code>NULLIF</code> handles the
        all-stopword case, since an empty tsquery emits a notice.
      </p>

      <Callout kind="production">
        <p>
          This is string surgery on a rendered tsquery, and it is safe only because Postgres always
          quotes lexemes and pads operators with spaces. A real BM25 engine exposes per-clause
          operators directly and needs none of it. It is pinned by four regression tests, two of
          them pure and two integration — the integration one plants a decoy error code and asserts
          it does <em>not</em> match.
        </p>
      </Callout>

      <H2 id="vector-leg">The vector leg</H2>
      <p>
        384-dimension embeddings from <code>bge-small-en-v1.5</code>, L2-normalised, in a{" "}
        <code>vector(384)</code> column with an HNSW index. The dimension is hardcoded in the schema
        rather than left untyped, deliberately: the type check is what catches a model-mismatch bug
        at insert time, which is exactly the class of silent corruption the database should refuse.
      </p>
      <p>
        <code>hnsw.ef_search</code> is set to 100 per query rather than left at pgvector&apos;s
        default of 40. The default is calibrated for an unfiltered index; once a selective tenant
        predicate discards most of the beam, a beam of 40 is too narrow and recall quietly drops on
        exactly the tenants with the least data.
      </p>

      <Callout kind="caution" title="Switching embedding model is a re-ingest, not a config change">
        <p>
          Embeddings from different models live in different spaces and are not comparable — you can
          never mix them in one index. Moving to a 768-dimension model means a column migration, a
          reindex, <em>and</em> a full re-ingest of every document.
        </p>
      </Callout>

      <H2 id="fusion">Reciprocal rank fusion</H2>
      <CodeBlock
        language="python"
        filename="app/retrieval/fusion.py"
        code={`score(d) = Σ_legs  weight_leg / (k + rank_leg(d))        # k = 60`}
      />
      <p>
        The two legs produce scores on incompatible scales: <code>ts_rank_cd</code> is unbounded and
        depends on term frequencies in this corpus, cosine similarity is bounded and depends on the
        query. &ldquo;0.83&rdquo; means something entirely different in each. So fusion consumes
        only ranked id lists — it is scale-free, and there is no normalisation step to get wrong.
      </p>

      <H3 id="why-not-weighted">Why not weighted score fusion</H3>
      <p>
        The obvious approach, and worse than it looks. Min-max normalising each leg&apos;s returned
        window makes every leg&apos;s best result 1.0 and its worst 0.0, which{" "}
        <strong>destroys the information that a leg found nothing good</strong>. A leg whose top hit
        is garbage still contributes a confident 1.0. It also needs per-corpus weight tuning that
        has to be redone whenever the corpus changes. Z-scores need a distribution that is not
        available at query time, and keyword scores are nowhere near normal. Learning to rank is the
        right answer at scale and needs labelled data that 65 cases are not.
      </p>

      <Callout kind="result" title="Agreement beats a single rank-1 hit until rank 62">
        <p>
          Because <code>2/(k+r) &lt; 1/(k+1)</code> exactly when <code>r &gt; k+2</code>. With
          twenty-candidate legs, <strong>a chunk found by both legs always outranks a chunk found by
          one</strong> — which is the behaviour hybrid retrieval is supposed to produce, and it
          falls out of the arithmetic rather than being coded as a rule. It also means per-leg
          candidate depth is a real tuning knob rather than a formality. Pinned by a test named
          after the crossover.
        </p>
      </Callout>

      <p>
        A broken leg returning nonsense can contribute at most <code>weight/(k+1)</code> per
        document, so it degrades the ranking gently instead of destroying it. The sort key is total
        — score, then leg count, then best rank, then chunk id — because two documents at rank 1 in
        different legs have <em>identical</em> scores, and without a deterministic final key their
        order depends on dictionary insertion. Evaluation metrics would then reshuffle between
        identical runs, which is a day spent chasing a phantom regression.
      </p>
      <p>
        What fusion gives up: it is blind to <em>margin</em>. If the keyword leg&apos;s first result
        is an exact error-code hit and its second is unrelated, fusion treats that gap the same as a
        near-tie.
      </p>

      <H2 id="reranking">The cross-encoder</H2>
      <p>
        <code>bge-reranker-base</code> scores query–chunk pairs jointly rather than comparing two
        independently-computed vectors, which is why it is more accurate and why it cannot be
        precomputed. It outputs a raw logit, roughly −11 to +11.
      </p>
      <p>
        Both numbers are persisted: a sigmoid of the logit, which every gate and threshold reads, and
        the raw logit itself. A gate that never fires is debuggable only if you can see the
        distribution the model actually produced; keeping only the squashed value loses that, and
        keeping only the logit puts every downstream threshold on an unbounded model-specific scale.
        Sorting uses the raw logit, since a sigmoid is monotonic but saturates at the extremes.
      </p>
      <p>
        Softmax over the candidate set was rejected: it makes each score <em>relative to whatever
        else was retrieved alongside</em>, so the same chunk scores differently depending on its
        company. A confidence gate needs an absolute signal.
      </p>

      <Callout kind="caution" title="It costs more than the entire latency budget">
        <p>
          Mean 1.7–3.3 seconds on a 12-thread CPU, against a target of P95 under three seconds for
          the whole request. Reranking cost is linear in pairs, so only the top{" "}
          <strong>eight</strong> candidates reach it — roughly 2.5x faster, and recall@20 still
          measures the same twenty chunks because retrieval itself was not narrowed. What that
          accepts: a chunk fusion ranked ninth that the cross-encoder would have promoted to first is
          now unreachable.
        </p>
      </Callout>

      <H3 id="conditional">Conditional reranking, and why it ships disabled</H3>
      <p>
        Reranking only when the top scores are ambiguous is the obvious latency optimisation. It is
        fully implemented, fully tested, and <strong>off by default</strong> — because always-rerank
        is the quality <em>ceiling</em> the evaluation measures the gate against. Shipping it on
        would make the gated arm the baseline and quietly delete the comparison. &ldquo;Conditional
        reranking saves 280 ms and costs 1.2 points of recall@5&rdquo; is a finding;
        &ldquo;conditional reranking is on&rdquo; is not.
      </p>
      <p>
        The rule is <code>margin = (s₁ − s₅) / s₁</code> over <em>fused</em> scores, because those
        depend only on ranks and <code>k</code> and therefore occupy the same numeric range for every
        query — the only thing that makes a relative threshold portable across queries.
      </p>

      <Callout kind="result" title="The threshold was measured, and the first guess was wrong by 4x">
        <p>
          The default was 0.30, and the arithmetic caps the real value far below it. When every
          top-5 candidate is found by both legs — 13 of 20 overlap was typical — the fused scores are{" "}
          <code>2/(k+1) … 2/(k+5)</code>, and that shape has a hard ceiling of{" "}
          <span className="figure">0.062</span>. The moment a single-leg chunk breaks into the top
          five, the margin jumps to <span className="figure">0.531</span>.
        </p>
        <p className="mt-2">
          So the margin was never measuring &ldquo;how confident is the top result&rdquo;. It
          measures <strong>&ldquo;was the top five unanimous&rdquo;</strong> — a near-binary signal.
          The default moved to 0.10, just above the all-agree ceiling. Observed margins since:
          0.055, 0.059, 0.076, 0.076. <strong>At 0.10 the gate still never fires.</strong>
        </p>
      </Callout>

      <p>
        Which reframes the open question from &ldquo;what threshold?&rdquo; to{" "}
        <em>is the fusion margin a usable ambiguity signal at all?</em> Fusion compresses scores hard
        by design — that is what <code>k = 60</code> is for — so the dynamic range available to
        threshold on may simply be too narrow. If a sweep over 0.03–0.15 finds no threshold trading
        latency for acceptable recall, the alternative is gating on raw per-leg scores, at the cost
        of the cross-query comparability that made fused scores attractive in the first place. That
        is a real tension between two decisions in this system, and it should be resolved with data
        rather than argued.
      </p>

      <H2 id="isolation">Isolation, structurally</H2>
      <p>
        Neither leg ever writes a full query. A leg supplies a projection, a predicate and an
        ordering, and the scope composes the real SQL with{" "}
        <code>WHERE c.tenant_id = $1 AND c.is_current</code> welded on unconditionally.{" "}
        <code>$1</code> belongs to the scope; leg parameters start at <code>$2</code>.
      </p>
      <p>
        <Link href="/docs/tenant-isolation">The four layers that keep that honest →</Link>
      </p>
    </DocPage>
  );
}
