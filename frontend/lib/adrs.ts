/**
 * The decision record, as data.
 *
 * Kept in one module rather than inline in the page so the record has a shape:
 * every entry must carry a context, a decision, and the alternatives that were
 * rejected with the reason. A record where an entry can omit its alternatives
 * degenerates into a changelog — "we did X" is not a decision, it is a fact.
 *
 * The prose here is compressed from `docs/decisions.md`, which stays the
 * canonical long form. Entries are never rewritten once published; a superseded
 * one gets a note instead.
 */

export interface Alternative {
  option: string;
  rejected: string;
}

export interface Adr {
  id: string;
  title: string;
  phase: string;
  context: string;
  decision: string;
  alternatives: Alternative[];
  /** A consequence, a cost accepted, or an honest caveat. Optional. */
  note?: string;
}

export const ADRS: Adr[] = [
  {
    id: "ADR-001",
    title: "BM25 via Postgres full-text search, not a dedicated engine",
    phase: "Foundations",
    context:
      "Hybrid retrieval needs a keyword-matching leg beside vector search, and that leg has to respect the same tenant boundary.",
    decision:
      "A generated tsvector column on chunks with a GIN index, ranked with ts_rank_cd. One datastore serves both retrieval legs.",
    alternatives: [
      {
        option: "A Python BM25 library",
        rejected:
          "True BM25 scoring, and the index lives in process memory — rebuilt on every restart and for every worker, with tenant filtering happening in Python AFTER scoring. That is exactly the application-level isolation this system is built to avoid.",
      },
      {
        option: "Elasticsearch or OpenSearch",
        rejected:
          "Real BM25 and a real operational burden: a second datastore to keep consistent with Postgres, for a corpus of 312 chunks.",
      },
    ],
    note:
      "ts_rank_cd is not BM25 — it lacks length normalisation and IDF saturation. For similar-length chunks the ranking behaviour is close enough, and rank fusion consumes only ranks, which mutes the difference further. The tsquery itself took three versions to get right; see field note 1.",
  },
  {
    id: "ADR-002",
    title: "Raw numbered SQL migrations, not a migration framework",
    phase: "Foundations",
    context: "The schema needs versioned, repeatable migrations.",
    decision:
      "Numbered .sql files applied in filename order by a ~50-line script, tracked in a schema_migrations table, each file in one transaction.",
    alternatives: [
      {
        option: "Alembic",
        rejected:
          "The industry standard, and autogenerate hides the DDL. A learning goal here is that you can write this schema on a whiteboard. The migration graph is linear and solo-authored, so branches and downgrades buy nothing — roll forward instead.",
      },
    ],
    note:
      "A team would use Alembic, sqitch or atlas for autogenerate-with-review, downgrade testing and multi-developer merge safety.",
  },
  {
    id: "ADR-003",
    title: "Stateless chat history",
    phase: "Foundations",
    context:
      "Multi-turn query rewriting needs conversation history. Either the server keeps a sessions table, or the client sends history with each request.",
    decision:
      "The client sends prior turns plus a client-generated conversation id. History is used transiently for rewriting; the id is persisted on the trace row for observability only.",
    alternatives: [
      {
        option: "A server-side sessions table",
        rejected:
          "Adds a write path, a consistency question on retries, and session garbage collection — none of which teach anything about RAG. The pipeline itself is stateless: history is an INPUT to rewriting, not server state.",
      },
    ],
    note:
      "Request payloads grow with conversation length, bounded by the client sending the last N turns. A product needing cross-device resume would add a sessions service IN FRONT of this stateless core; the pipeline would not change.",
  },
  {
    id: "ADR-004",
    title: "The heading path is prepended into chunk content",
    phase: "Ingestion",
    context:
      "Both the keyword index and the embedding are computed from the content column, so this is decided at ingestion time and reversing it means re-chunking and re-embedding everything.",
    decision:
      "Docs chunks store `Billing > Invoices > Proration\\n\\n<body>`. The clean path is also kept in its own column for display and filtering.",
    alternatives: [
      {
        option: "Metadata-only heading path",
        rejected:
          "Keeps content pure and loses the retrieval signal entirely. A section body often never repeats its own topic words, so the chunk becomes unfindable for the obvious query.",
      },
      {
        option: "A separate embedding_text column",
        rejected:
          "Maximum control, and two copies of every chunk that can drift apart — and full-text search wants the heading terms too.",
      },
    ],
    note:
      "Costs 10–20 tokens per chunk against the 300–500 budget, accounted for in the chunker. Benefits both retrieval legs at once, which is why it beats either alternative.",
  },
  {
    id: "ADR-005",
    title: "Embedding dimension fixed at 384 in the schema",
    phase: "Foundations",
    context: "pgvector columns and HNSW indexes require a fixed dimension.",
    decision:
      "The schema hardcodes vector(384), matching the default model. Switching models is supported by config and requires a column migration, a reindex, and a full re-ingest.",
    alternatives: [
      {
        option: "An untyped vector column",
        rejected:
          "Loses the dimension check that catches a model-mismatch bug at insert time — exactly the class of silent corruption the database should refuse.",
      },
    ],
    note:
      "Embeddings from different models live in different spaces and are never comparable; you can never mix them in one index. Paid models supporting Matryoshka truncation make dimension migration cheaper.",
  },
  {
    id: "ADR-006",
    title: "Raw httpx for every LLM provider — no vendor SDKs",
    phase: "Foundations",
    context: "Four providers, each with an official Python SDK.",
    decision:
      "One implementation per wire dialect — an OpenAI-compatible one covering three providers, plus one for Gemini. Roughly 250 lines total.",
    alternatives: [
      {
        option: "The official SDKs",
        rejected:
          "Four SDKs means four exception hierarchies to normalise into one error taxonomy, and four dependencies to version-chase. They also hide SSE framing, Retry-After handling and error taxonomies — the three things worth being able to explain from code you wrote.",
      },
    ],
    note:
      "We own wire-format drift, mitigated by a smoke test that fails fast and loudly. A follow-on decision: a Retry-After larger than the maximum wait means quota exhaustion rather than congestion, so the client fails over immediately instead of sleeping through a delay that was never going to help.",
  },
  {
    id: "ADR-007",
    title: "The eval harness is a first-class package",
    phase: "Evaluation",
    context: "The harness needs a home and a CLI.",
    decision:
      "It lives in fishnet/ with `python -m fishnet.run` as the entry point — a named component rather than a scripts directory.",
    alternatives: [
      {
        option: "An evals/ folder of scripts",
        rejected:
          "Scripts do not get imports, tests, or a stable interface. The harness is a product surface here, not tooling.",
      },
    ],
  },
  {
    id: "ADR-008",
    title: "Hybrid synthetic corpus — declared facts, generated prose, committed output",
    phase: "Ingestion",
    context:
      "The golden set must map queries to known-correct sources, which is only possible if the corpus contents are known with certainty.",
    decision:
      "Every document, version, date, error code and planted conflict is declared in Python. Only body prose is generated, keyed by prompt hash into a committed cache, with a deterministic template fallback.",
    alternatives: [
      {
        option: "Fully templated",
        rejected:
          "Perfectly reproducible, and the prose is formulaic enough that retrieval becomes unrealistically easy — lexical overlap with queries is artificial.",
      },
      {
        option: "Fully LLM-generated",
        rejected:
          "Realistic, and the facts drift. A model asked for sixty doc pages invents its own error codes and contradicts itself; regeneration silently changes ground truth.",
      },
    ],
    note:
      "A guardrail warns when a required literal from the brief does not survive into generated text — a warning rather than a failure, because a hundred-document run should not abort, but you must know before building a golden set on it.",
  },
  {
    id: "ADR-009",
    title: "Two kinds of planted stale data",
    phase: "Ingestion",
    context:
      "Stale data is the interview-critical failure mode, and a corpus with only one kind of conflict can only demonstrate one defence.",
    decision:
      "Plant both. Declared supersession archives the old document; an unmarked conflict leaves both live and tags the contested chunks.",
    alternatives: [
      {
        option: "Auto-archive the conflicting document too",
        rejected:
          "The changelog contradicts one FACT on the page, not the page. Archiving would destroy correct information to fix one stale sentence.",
      },
    ],
    note:
      "The unmarked conflict is the realistic case: in production nobody remembers to mark the old doc. A system that only handles declared supersession handles the easy half of the problem.",
  },
  {
    id: "ADR-010",
    title: "Token counting with the embedding model's own tokenizer",
    phase: "Ingestion",
    context: "Chunk budgets are meaningless unless measured with the tokenizer that will process the text.",
    decision:
      "The real pipeline wraps the model's own tokenizer; tests inject an approximate counter so the suite needs no torch.",
    alternatives: [
      {
        option: "Character or word heuristics",
        rejected:
          "A chunk that is '450 tokens' by word count can be 700 real tokens. It gets stored whole, embedded TRUNCATED at the model's limit, and retrieval quietly degrades with nothing in any log.",
      },
    ],
    note:
      "Per-unit counts are not additive — joining adds separators and subword merging differs across boundaries — so the chunker measures the joined candidate and runs a final enforcement pass. Summing parts underestimates, which is how a chunk sneaks past the cap.",
  },
  {
    id: "ADR-011",
    title: "Reciprocal rank fusion, not weighted score fusion",
    phase: "Retrieval",
    context:
      "The two legs produce scores on incompatible scales: an unbounded corpus-dependent keyword rank and a bounded query-dependent cosine similarity. '0.83' means something entirely different in each.",
    decision:
      "score(d) = Σ weight / (k + rank), with k = 60, as a pure function consuming only ranked id lists.",
    alternatives: [
      {
        option: "Weighted score fusion with min-max normalisation",
        rejected:
          "Normalising each leg's window makes every leg's best result 1.0 and its worst 0.0, which DESTROYS the information that a leg found nothing good. It also needs per-corpus weight tuning redone whenever the corpus changes.",
      },
      {
        option: "Z-score normalisation",
        rejected: "Needs a score distribution unavailable at query time, and keyword scores are nowhere near normal.",
      },
      {
        option: "Learning to rank over both scores",
        rejected: "The right answer at scale, and it needs labelled data that 65 cases are not.",
      },
    ],
    note:
      "Agreement beats a single rank-1 hit until rank 62, so with 20-candidate legs a chunk found by both legs always outranks one found by one — emergent arithmetic rather than a coded rule. The sort key is total (score, leg count, best rank, chunk id) because without a deterministic tiebreak, eval metrics reshuffle between identical runs.",
  },
  {
    id: "ADR-012",
    title: "Tenant isolation enforced by a query-builder scope",
    phase: "Retrieval",
    context:
      "The requirement is not 'remember to filter' — it is that a developer cannot write the unsafe query, because the failure being defended against is silent.",
    decision:
      "One object may read the chunks table. Legs supply fragments; the scope composes the SQL and welds the tenant predicate on unconditionally. Four layers: composition, construction-time fragment guards, a runtime tripwire, and a source lint.",
    alternatives: [
      {
        option: "Convention plus code review",
        rejected: "What most codebases do, and it works until the one pull request that adds a quick debug query.",
      },
      {
        option: "A decorator on leg functions",
        rejected: "Nothing stops a developer from not applying it.",
      },
      {
        option: "Postgres row-level security",
        rejected:
          "Strictly better and orthogonal rather than alternative — it belongs UNDERNEATH all of this, and is noted in the initial migration for whoever touches the schema next.",
      },
    ],
    note:
      "The tripwire raises rather than filtering. Dropping offending rows would serve a slightly-wrong result set that nobody notices; a leak Python quietly corrects is a leak nobody investigates. Crashing produces an incident, which produces a fix.",
  },
  {
    id: "ADR-013",
    title: "The reranker's score is a sigmoid, and both numbers are stored",
    phase: "Retrieval",
    context:
      "The cross-encoder outputs a raw logit, not a probability, while every other score in the pipeline is in [0, 1].",
    decision:
      "Persist the sigmoid — which gates and thresholds read — and the raw logit. Sort on the logit, since sigmoid is monotonic but saturates.",
    alternatives: [
      {
        option: "Softmax over the candidate set",
        rejected:
          "Makes each score relative to whatever else was retrieved alongside, so the same chunk scores differently depending on its company. A confidence gate needs an absolute signal.",
      },
      {
        option: "Keep only one of the two numbers",
        rejected:
          "Only the sigmoid, and a gate that never fires becomes undebuggable. Only the logit, and every downstream threshold is on an unbounded model-specific scale.",
      },
    ],
  },
  {
    id: "ADR-014",
    title: "Conditional reranking ships disabled",
    phase: "Retrieval",
    context:
      "Reranking only when the top scores are ambiguous buys most of the quality for a fraction of the latency.",
    decision:
      "Fully implemented, fully tested, and off by default — because always-rerank is the quality CEILING the evaluation measures the gate against.",
    alternatives: [
      {
        option: "Ship it on",
        rejected:
          "That makes the gated arm the baseline and quietly deletes the comparison. 'Conditional reranking saves 280 ms and costs 1.2 points of recall@5' is a finding; 'conditional reranking is on' is not.",
      },
    ],
    note:
      "The threshold was 0.30 and the arithmetic caps real margins at 0.062 — wrong by 4x, in the direction that made the feature invisible. Moved to 0.10, where it STILL never fires. So it is implemented and not yet demonstrated to do anything on this corpus, and it must not be described as a working latency optimisation.",
  },
  {
    id: "ADR-015",
    title: "The confidence gate reads two thresholds, chosen by which score is present",
    phase: "Generation",
    context:
      "The number being thresholded is a reranker sigmoid when reranking ran and a fusion score when it did not. Those scales differ by roughly 30x.",
    decision:
      "Two settings. The gate inspects the top result, picks the threshold by whether a reranker score exists, and records the score kind on the decision.",
    alternatives: [
      {
        option: "One threshold",
        rejected:
          "Calibrated for at most one scale and silently wrong for the other. Set for the reranker it abstains on everything unreranked; set for fusion it passes everything reranked. Both present as 'the gate isn't working'.",
      },
      {
        option: "Normalise both onto a common scale",
        rejected: "The same normalisation problem rejected for fusion, with the same absence of a principled normaliser.",
      },
    ],
    note:
      "The score kind is read from the DATA, not from config — config knows the intent, only the result knows what happened. And it is recorded because top_score = 0.02 is uninterpretable six weeks later: a trace that cannot be read is not observability.",
  },
  {
    id: "ADR-016",
    title: "Citation validation by embedding similarity, not entailment",
    phase: "Generation",
    context: "A post-hoc check that a cited chunk actually contains semantically similar content.",
    decision:
      "Split the answer into sentence-level claims, embed each with the same local encoder retrieval uses, compare against the cited chunks, in ONE batched call.",
    alternatives: [
      {
        option: "LLM-as-judge",
        rejected:
          "Much stronger — it catches contradiction, not just topical drift. Costs a call per answer, adds seconds, burns the quota the evaluation needs, and introduces a second model whose failures correlate with the generator's.",
      },
      {
        option: "An NLI model",
        rejected:
          "The technically right answer, and another ~1.4 GB model on a CPU already spending seconds on reranking. The latency would land on every answer.",
      },
    ],
    note:
      "The hole, stated plainly: similarity catches 'this citation is unrelated' and cannot catch 'this citation says the opposite'. Every identifier in the module says `similarity`, never `entailment` — a hole named at every call site is one you cannot forget.",
  },
  {
    id: "ADR-017",
    title: "Query rewriting is skipped on the first turn, and its output is validated",
    phase: "Generation",
    context: "Resolving follow-ups into standalone queries costs an LLM call on the critical path.",
    decision:
      "Skip entirely when there is no history. Otherwise feed the last six turns at temperature 0.0, and validate the output before using it.",
    alternatives: [
      {
        option: "Always rewrite",
        rejected:
          "A question with no conversation behind it is standalone by definition. Most support sessions are a single turn, so this is not a micro-optimisation.",
      },
      {
        option: "Trust the rewriter's output",
        rejected:
          "The dominant failure of a rewriting prompt is that the model ANSWERS the question instead of rewriting it — and then the corpus is searched for the text of a hallucinated response, a spectacular retrieval bug that raises nothing.",
      },
    ],
    note:
      "History is rendered as data rather than replayed as turns, because we want the model analysing the conversation, not participating in it. Failure is never fatal: a degraded rewrite gives worse retrieval, an exception gives no answer at all.",
  },
  {
    id: "ADR-018",
    title: "Three abstention paths, one exit, all counted as escalations",
    phase: "Generation",
    context:
      "The system can decline for three unrelated reasons: weak retrieval, the model declining after reading the context, or every provider failing.",
    decision: "All three route through one function, write an escalation row, and set the same trace action.",
    alternatives: [
      {
        option: "Handle each path where it occurs",
        rejected:
          "Three code paths setting the escalation row, the trace action and the user-facing sentence independently is exactly how an escalation-rate metric ends up lying about the system it measures.",
      },
      {
        option: "Count only gate abstentions",
        rejected:
          "The escalation rate would understate reality and look healthy while the system degraded. The model's own abstention is the more interesting signal anyway — it means retrieval found plausible chunks that did not contain the answer, which is a corpus gap rather than a retrieval bug.",
      },
    ],
    note:
      "Every abstention writes a row, including obviously out-of-scope questions. A cluster of those is the single clearest signal of what customers ask that you have not documented, and it is invisible if you only record near-misses.",
  },
  {
    id: "ADR-031",
    title: "Greetings are matched before the pipeline, not answered by the model",
    phase: "Generation",
    context:
      "The confidence gate sits before generation, which is right for questions and wrong for \"hi\". A greeting retrieves nothing, scores below threshold, abstains, and opens an escalation — so saying hello put a ticket in a human agent's queue.",
    decision:
      "A pure function over a closed set of anchored phrasings runs before every other stage. It answers greetings, thanks, goodbyes and \"what are you\" with fixed text, and returns nothing for anything it does not recognise — which falls through to the real pipeline.",
    alternatives: [
      {
        option: "Let the model handle greetings",
        rejected:
          "The obvious fix, and it costs the whole guarantee. The moment the model may answer without retrieved context, it may do so for ANY question — closed-book generation is not a behaviour you can enable for one message class and disable for the rest.",
      },
      {
        option: "Lower the confidence threshold so greetings pass",
        rejected:
          "Solves the symptom by disabling the defence. The gate would then also pass the topically-adjacent-but-unanswerable questions it exists to catch.",
      },
      {
        option: "Embedding similarity against a set of example greetings",
        rejected:
          "Fuzzy by construction, and the failure direction is the dangerous one: a real question scoring close to a greeting gets a canned non-answer. Anchored literals cannot do that.",
      },
    ],
    note:
      "The safety property is tested against the golden set itself: a test asserts that none of the 65 cases, nor any user turn in their histories, is intercepted. If the matcher ever swallowed one, 16 must-abstain assertions would start passing for entirely the wrong reason. No trace row is written for these replies — nothing observable happened, and recording a 0.0 confidence from a request that never had one would corrupt mean_confidence on the dashboard.",
  },
  {
    id: "ADR-032",
    title: "The wordmark is drawn in the repository, not licensed",
    phase: "Frontend",
    context: "The product needed a real mark and a favicon. The obvious route is a stock logo from a marketplace.",
    decision:
      "An original leaping-fish silhouette, authored as four SVG paths in components/ui/Icon.tsx and mirrored in app/icon.svg for the browser tab.",
    alternatives: [
      {
        option: "Stock artwork",
        rejected:
          "Fast, and it puts a licensing question on a portfolio piece that is otherwise entirely first-party. A watermarked comp is not usable at all, and the licence for a cleaned one has to be held and evidenced.",
      },
      {
        option: "A generated raster logo",
        rejected:
          "Fixed resolution, no theme awareness, and a PNG favicon is soft on a high-DPI tab.",
      },
    ],
    note:
      "The fish is authored facing left on a level axis and the whole group is then rotated into the leap, so changing the angle is one number rather than twenty re-derived coordinates. The dorsal crest's base sits INSIDE the body outline so the shapes merge into one silhouette instead of reading as a fin stuck onto a fish — that is the difference between the mark working and not working at 16px. 0.76 is the largest scale at which the tail still clears the tile's corner radius, chosen by rendering at 16, 20, 26, 32, 48 and 72px and looking.",
  },
  {
    id: "ADR-019",
    title: "Golden-set ground truth is a stable locator, not a chunk id",
    phase: "Evaluation",
    context: "Each case must say which chunks a query should retrieve. Chunk ids are UUIDs generated at ingest time.",
    decision:
      "Store a source locator — source type plus slug and heading, or an entry or ticket id — and resolve it to chunk ids at the start of every run.",
    alternatives: [
      {
        option: "Chunk UUIDs",
        rejected:
          "Re-ingesting invalidates the entire golden set silently: every case points at rows that no longer exist, recall drops to zero, and it presents as a catastrophic retrieval regression with no cause.",
      },
      {
        option: "Content hashes",
        rejected: "Stable only while the chunker produces byte-identical text — and moving chunk boundaries is what the chunking experiment does.",
      },
    ],
    note:
      "The decisive argument: the naive chunking arm produces entirely different chunks, so ground truth in one arm's chunk ids cannot score the other. With UUIDs the experiment is not awkward, it is impossible.",
  },
  {
    id: "ADR-020",
    title: "The judge is a different model, on a different provider chain",
    phase: "Evaluation",
    context: "Faithfulness and citation accuracy are scored by an LLM.",
    decision:
      "Generate with an 8B model, judge with a 70B one at temperature 0.0, built on a separate client with a reversed provider order. The judge model is stamped on every score.",
    alternatives: [
      {
        option: "The same model judging itself",
        rejected:
          "It shares its own blind spots. If the generator misreads a chunk, the same model asked 'is this faithful?' misreads it identically and says yes — so it measures agreement with itself rather than correctness.",
      },
      {
        option: "A different model on the same chain",
        rejected:
          "A rate-limited judge silently falls back onto the exact model it is grading. The correlated-failure problem reintroduced through the back door, invisibly.",
      },
      {
        option: "Two judges, reporting disagreement",
        rejected:
          "More rigorous, and disagreement rate is itself a useful reliability signal — rejected for now because it doubles quota consumption on a free tier the evaluation already strains.",
      },
    ],
    note:
      "Judge scores are a noisy estimator, not a measurement. That is why quality metrics carry a 5% tolerance and hard assertions carry none, and why skipped judgements are excluded rather than counted as zero.",
  },
  {
    id: "ADR-021",
    title: "The golden set is derived from the corpus specification",
    phase: "Evaluation",
    context: "About sixty cases mapping queries to known-correct sources across six case types.",
    decision:
      "A script derives cases from the corpus spec; the output is committed and meant to be hand-edited afterwards.",
    alternatives: [
      {
        option: "Hand-written from scratch",
        rejected: "A day of work, and every re-ingestion risks invalidating ground truth someone guessed at.",
      },
      {
        option: "LLM-generated cases",
        rejected:
          "Produces plausible questions with plausible expected sources — and 'plausible' is exactly the failure mode an eval harness exists to detect. Ground truth that was itself generated cannot be trusted to grade generation.",
      },
    ],
    note:
      "Query phrasing for normal and multi-turn cases stays hand-written, because a question has to be something a customer would actually type. The spec gives what is true; a human gives what someone would ask.",
  },
  {
    id: "ADR-022",
    title: "Two tolerances — 5% on quality, zero on correctness",
    phase: "Evaluation",
    context: "CI must fail when the system gets worse, without failing on noise.",
    decision:
      "Quality metrics fail on a >5% relative drop against a committed baseline. Hard assertions fail on any failure.",
    alternatives: [
      {
        option: "One tolerance for everything",
        rejected:
          "There is no acceptable rate of cross-tenant leakage, and a percentage band on a security check is how a bug gets absorbed by a quality budget.",
      },
      {
        option: "Compare against the previous run",
        rejected:
          "Lets quality erode one tolerated 4% drop at a time, each individually acceptable, none ever noticed. Committing a baseline is a deliberate act with a reviewable diff.",
      },
    ],
    note:
      "Three rules that matter more than the number: improvements never fail; no baseline is a pass; generation metrics are skipped when the judge ran on under 25% of cases, because a score over eight cases against a baseline over sixty is not a comparison.",
  },
  {
    id: "ADR-023",
    title: "The cache key is the rewritten query, and the cache sits after rewriting",
    phase: "Caching",
    context: "Both rewriting and the cache want to run first.",
    decision: "Rewrite, then check the cache, keyed on the rewritten query.",
    alternatives: [
      {
        option: "Cache on the raw query, before rewriting",
        rejected:
          "'What about the backoff?' means something different in a conversation about webhooks than in one about rate limits — the same four words, two correct answers. Keying on the raw query serves one conversation's answer into another, which is a correctness bug that looks exactly like a hallucination.",
      },
      {
        option: "Cache on both keys",
        rejected: "Doubles the hit rate on repeated follow-ups and reintroduces the collision. The raw key is unsafe no matter what sits beside it.",
      },
    ],
    note:
      "The rewritten query is standalone BY CONSTRUCTION — that is the entire property rewriting produces, and precisely what a cache key needs. Cost: a cache hit on a follow-up still pays for one rewrite call.",
  },
  {
    id: "ADR-024",
    title: "Two guardrails make a 0.95 semantic threshold survivable",
    phase: "Caching",
    context:
      "A semantic cache serves an answer written for a different question, which makes it the most dangerous component in the system: the failure is silent, durable, and looks like a hallucination.",
    decision:
      "Keep 0.95, and add two hard guardrails: identifier-bearing queries skip the semantic path entirely, on read AND write; abstentions are never cached.",
    alternatives: [
      {
        option: "Raise the threshold to 0.98",
        rejected:
          "Reduces but does not remove the identifier problem — two error codes can exceed 0.98 — while cutting the hit rate enough to undermine the cost argument the cache exists for.",
      },
      {
        option: "Drop the semantic cache",
        rejected: "Safest, and abandons the primary lever for cost control.",
      },
    ],
    note:
      "The identifier detector is deliberately broad: a false positive costs one cache miss, a false negative serves the wrong error code's answer. And 0.95 remains a design number, not a validated one — recorded as open rather than quietly assumed correct.",
  },
  {
    id: "ADR-025",
    title: "Active invalidation through a chunk-to-keys reverse index",
    phase: "Caching",
    context:
      "The corpus contains deliberately planted stale-data conflicts, so a cache that keeps serving pre-update answers recreates the exact failure the system exists to prevent.",
    decision:
      "Every cached answer records which chunks it was built from. Re-ingesting a document deletes precisely the answers built on them.",
    alternatives: [
      {
        option: "Wipe the tenant's whole cache on any change",
        rejected: "Simple and correct. Re-ingestion is routine, so the hit rate would spend most of its life near zero.",
      },
      {
        option: "TTL only",
        rejected: "Least code, and serves a stale answer for up to an hour after a correction ships.",
      },
    ],
    note:
      "Three details are the actual decision: chunk ids are collected BEFORE the delete; archived chunks are included, because an answer cached before a supersession is exactly the stale one; and invalidation runs AFTER the commit, because clearing the cache for content that still exists costs a few LLM calls while the reverse costs trust.",
  },
  {
    id: "ADR-026",
    title: "A cache hit reports zero cost, and triage is heuristic",
    phase: "Caching",
    context: "Two smaller decisions, both about not letting instrumentation lie.",
    decision:
      "A cache hit records zero tokens and zero cost, keeping only the original provider and model. Feedback is classified by heuristic from signals already on the trace row.",
    alternatives: [
      {
        option: "Replay the original spend on a cache hit",
        rejected:
          "Cost-per-query would RISE as caching improved. The dashboard would show the system getting more expensive exactly as it got cheaper, on the metric caching exists to move.",
      },
      {
        option: "An LLM classifier for triage",
        rejected:
          "Costs quota, varies run to run, and cannot be checked. Every signal needed is already on the trace, so classification is free, instant, deterministic and explainable.",
      },
    ],
    note:
      "The check ORDER is the real design: cache, then stale data, then retrieval, then generation. And `unclear` is a real category — a misclassified failure is worse than an unclassified one, because it points at the wrong component with confidence and the real bug survives the investigation.",
  },
  {
    id: "ADR-027",
    title: "The frontend talks to the API through a rewrite, not CORS",
    phase: "Frontend",
    context: "The browser needs to reach FastAPI.",
    decision:
      "Every frontend call goes to a relative /api path, which the Next server rewrites onto the API origin. No CORS middleware exists anywhere in the system.",
    alternatives: [
      {
        option: "Direct calls plus CORS middleware",
        rejected:
          "More explicit, and it adds a config surface whose failure mode is silent. CORS combined with a STREAMING response is genuinely nasty to debug: a wrong header produces a stream that just stops, with no useful error on either side. And allow_origins=['*'] is what people reach for when it breaks.",
      },
    ],
    note:
      "One environment variable covers Docker and local development, it is read on the Next server so it never reaches the browser, and it matches how this would actually deploy — a reverse proxy in front of both services.",
  },
  {
    id: "ADR-028",
    title: "Sources are always visible, not behind a click",
    phase: "Frontend",
    context: "The interface has to decide how prominent the evidence is.",
    decision:
      "A permanent panel listing every source offered to the model, rendered before the answer starts. Clicking a marker expands the matching source.",
    alternatives: [
      {
        option: "A click-to-open drawer",
        rejected:
          "The backend emits its citations BEFORE the first token specifically so the panel can populate while the answer types. A drawer wastes that: the evidence arrives early and sits hidden. And evidence behind a click is evidence most people never see, which makes the product's claim unfalsifiable in practice.",
      },
    ],
    note:
      "Originally accepted a real cost: below 1024px the panel disappeared entirely rather than becoming a drawer, recorded as a known gap rather than shipped half-built. ADR-029 closes it.",
  },
  {
    id: "ADR-029",
    title: "Documentation is the front door; the product sits behind one action",
    phase: "Frontend",
    context:
      "The root route used to be the chat interface. A stranger arriving from a link was dropped into an empty text box with no explanation of what the system was or which of its claims were measured.",
    decision:
      "The documentation set is the landing experience at /. The running product moved to /try, with the operations dashboard beside it, reachable from a single primary action in the header. Two route groups give each surface its own chrome without changing any API path.",
    alternatives: [
      {
        option: "Keep the chat at / and link out to docs",
        rejected:
          "Optimises for the returning user, who is not the audience. The first thirty seconds should establish what the system is and what it proves — the empty state cannot carry an architecture, an eval harness and a set of caveats.",
      },
      {
        option: "A marketing landing page separate from the documentation",
        rejected:
          "Two places to keep true, and the interesting claims here are technical ones. Making the overview page BE documentation page one means every claim on it is one click from its evidence.",
      },
    ],
    note:
      "The mobile sources panel arrived with this change, closing ADR-028's stated gap: a sheet below lg, triggered by a source-count button, opened automatically when a citation marker is tapped.",
  },
  {
    id: "ADR-030",
    title: "Zero runtime dependencies beyond React, including the icon set",
    phase: "Frontend",
    context:
      "The redesign needed an icon set, because emoji were being used as iconography — they render as a different picture on every platform, cannot inherit colour or stroke weight, and are announced by screen readers as their CLDR name mid-sentence.",
    decision:
      "Roughly thirty hand-drawn inline SVG icons on lucide's grid and stroke conventions, plus a token layer in Tailwind config. No icon library, no component library, no animation library, no charting library.",
    alternatives: [
      {
        option: "lucide-react and shadcn/ui",
        rejected:
          "The conventional answer, and it ships 1,500 glyphs so that thirty can be used, plus a component layer whose styling has to be overridden to match tokens that already exist here. Following lucide's conventions means swapping to the real package later is a one-line import change per call site.",
      },
      {
        option: "A charting library for the latency bars",
        rejected:
          "Four bars scaled to the slowest does not need 40 KB of JavaScript, and a div with a width is legible in the DOM inspector, which a canvas is not.",
      },
    ],
    note:
      "The cost is real and worth naming: the dropdown, the sheet and the scroll-spy are hand-written, so their accessibility is this codebase's responsibility rather than a library's. Each one documents the contract it owes — focus management, Escape, outside-click, aria-current.",
  },
];

/** Grouped for rendering, in build order rather than numeric order. */
export const ADR_PHASES = [
  "Foundations",
  "Ingestion",
  "Retrieval",
  "Generation",
  "Evaluation",
  "Caching",
  "Frontend",
] as const;
