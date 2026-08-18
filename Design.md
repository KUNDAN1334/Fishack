# RAG-based Customer Support System — Senior AI Engineer Interview Guide


## 1. High-Level Architecture

<img width="1154" height="798" alt="image" src="https://github.com/user-attachments/assets/f5a65580-5805-4710-9164-3fa853ae9c9d" />


### Component Explanation (Interview Talking Points)

| Component | Kya Karta Hai | Why Important |
|---|---|---|
| **Ingestion Pipeline** | Raw data ko clean, chunk, embed karke vector DB me daalta hai | Bina isse "garbage in garbage out" — retrieval hi kharab hoga |
| **Hybrid Retrieval** | BM25 (keyword) + vector (semantic) dono se candidates laata hai | Pure vector search exact terms (error codes, API names) miss karta hai |
| **Reranker** | Cross-encoder se top candidates ko dobara score karta hai | Bi-encoder (initial retrieval) recall ke liye good hai, precision ke liye nahi |
| **Confidence Gate** | Reranker score + retrieval score dekh ke decide karta hai answer dena hai ya nahi | Ye hallucination aur galat escalation dono rokta hai |
| **LLM Generation** | Retrieved chunks + query se grounded answer banata hai citations ke sath | Core "trust" layer — bina citation ke B2B support answer useless hai |
| **Escalation** | Low confidence ya explicit "talk to human" pe ticket create karta hai | SLA aur customer trust maintain karne ke liye zaroori |
| **Feedback Loop** | Thumbs up/down se system continuously improve hota hai | Production RAG system "static" nahi rehta — ye ek flywheel hai |

**Interview mein bolna:** "Ye ek classic Retrieval-Augmented Generation pipeline hai jisme main deliberately hybrid retrieval + reranking + explicit confidence gating add kar raha hoon, kyunki B2B support me galat answer dena, no answer dene se zyada costly hai."

---

## 2. Step-by-Step System Flow

### Query → Answer (Detailed)

1. **User query aata hai** (e.g., "Why is my webhook failing after the v2.3 update?")
2. **Query Rewriting (multi-turn context resolve)**
   - Agar ye follow-up hai (e.g., "what about the retry logic?"), toh LLM se query ko standalone bana dete hain using chat history.
   - Example: "what about retry logic?" → rewritten to "What is the retry logic for webhook failures after v2.3 update?"
3. **Guardrail check** — PII detection, prompt injection check, intent classification (support query vs. abuse vs. sales).
4. **Tenant isolation applied** — query tenant_id ke sath tag hoti hai, sirf uss tenant ka data search hoga.
5. **Hybrid Retrieval** — BM25 (exact match: "webhook", "v2.3") + vector search (semantic meaning) dono se top-20 chunks.
6. **Reranking** — cross-encoder model in 20 chunks ko query ke against re-score karta hai, top-5 nikalta hai.
7. **Confidence Scoring** — top reranked score threshold se compare hota hai (e.g., score < 0.4 → abstain).
8. **Branch A (Low confidence)** → "I don't have enough information" + escalate to human agent + ticket auto-create with context.
9. **Branch B (High confidence)** → top-5 chunks ko prompt me inject karke LLM se grounded, cited answer generate karte hain.
10. **Post-processing** — citation validation (kya cited chunk me actually wo claim hai?), formatting.
11. **Response return** — answer + source links + confidence indicator.
12. **Feedback capture** — user 👍/👎 deta hai, ye logged hota hai future improvement ke liye.

**Interview tip:** Always mention "query rewriting" step — bahut log isse miss karte hain aur multi-turn conversation follow-up questions me fail ho jata hai.

---

## 3. Data Ingestion Pipeline

### Sources & Handling

| Source | Ingestion Method | Frequency | Special Handling |
|---|---|---|---|
| **Product Docs (40+)** | Docs site crawler / CMS webhook | On publish/update (event-driven) | Version tagging, doc structure preserve karo (headings) |
| **Changelogs** | CI/CD pipeline hook (jab release ho) | Real-time on release | Timestamp critical — latest version priority |
| **Support Tickets** | Helpdesk API (Zendesk/Intercom) sync | Near real-time (webhook) or every 15 min batch | Only resolved + verified tickets, PII scrub |
| **Slack Threads** | Slack Events API | Real-time (on message/thread resolve) | Only "answered" threads, noise filter (casual chat exclude) |

### Continuous Ingestion Strategy

```
Source Event (webhook/poll) 
   → Extract & Clean 
   → Deduplicate (hash check)
   → Chunk 
   → Embed 
   → Upsert to Vector DB (with version + timestamp metadata)
   → Old version → soft-delete/archive (not hard delete, for audit)
```

- **Event-driven > Polling** jahan possible ho (docs CMS webhooks, Slack events) — latency kam, cost kam.
- **Batch polling** fallback ke liye (e.g., ticket system jo webhook support nahi karta) — every 10-15 min.

### Avoiding Stale Data Hallucination (IMPORTANT — interview favorite)

- **Versioning metadata**: Har chunk ke sath `effective_date`, `doc_version`, `is_current` flag store karo.
- **Retrieval-time filtering**: Query time pe sirf `is_current=true` chunks retrieve karo, unless user explicitly puraana version puchhe.
- **Changelog-aware re-ranking**: Agar retrieved doc chunk aur changelog dono relevant hain, changelog (recent) ko boost karo.
- **TTL-based re-embedding**: Docs jo frequently change hote hain (pricing, API limits) — unko higher priority re-crawl schedule do.
- **Conflict flag**: Agar do chunks contradict karte hain (old doc vs new changelog), system ko explicitly newest ko prefer karna chahiye based on timestamp, aur agar dono equally recent lage toh "let me confirm" abstain karo.

**Interview line:** "Stale data hallucination ka root cause almost hamesha missing/wrong metadata hota hai — isliye main ingestion time hi pe strong versioning discipline enforce karta hoon, generation time pe patch nahi karta."

---

## 4. Chunking Strategy (VERY IMPORTANT)

### Different Strategy per Source

| Source | Strategy | Why |
|---|---|---|
| **Product Docs** | **Structure-aware chunking** — split by heading/subheading (H2/H3), 300-500 tokens per chunk, with heading path as prefix metadata (e.g., "Webhooks > Retry Logic") | Docs already have logical structure — respecting it preserves context. Chunk overlap ~15% to avoid boundary cuts. |
| **Changelogs** | **Entry-level chunking** — 1 changelog entry = 1 chunk (usually small, 50-150 tokens), tagged with release version + date | Changelogs already atomic units hain — splitting further loses meaning, combining loses precision (which version did what) |
| **Support Tickets** | **Conversation-level chunking** — full resolved thread (question + accepted answer) as one chunk, or split at 500 tokens if very long; metadata: product_area, resolution_tag | Ticket ka value uske Q&A pair me hai — sirf question ya sirf answer chunk karna context tod deta hai |
| **Slack Threads** | **Thread-level chunking** — root message + replies till resolution marked, summarized if too long (LLM-based summarize + chunk) | Slack threads noisy hote hain (emojis, "thanks!", side chat) — raw chunking se garbage aata hai, isliye light LLM-based cleaning first |

### Large vs Small Chunks — Tradeoff (Classic Interview Question)

| | Small Chunks (100-200 tokens) | Large Chunks (800+ tokens) |
|---|---|---|
| **Precision** | High — retrieval bahut specific hota hai | Low — irrelevant info bhi aa jata hai, LLM ko "needle in haystack" |
| **Recall / Context** | Low — context lost ho sakta hai (e.g., ek step ka context doosre chunk me) | High — full context milta hai |
| **Cost** | Lower per chunk, but more chunks needed in top-K | Higher token cost per query |
| **Citation Accuracy** | Better — exact source sentence pinpoint ho sakti hai | Harder — bada chunk cite karna less useful for user |

### What I'd Choose & Why (Say this in interview)

- **Medium chunks (300-500 tokens) with semantic/structure-aware splitting + 10-15% overlap** — best balance.
- **Hierarchical chunking**: Small chunk for retrieval precision, but chunk ke sath parent section bhi link karo — jab LLM ko context chahiye, parent section bhi include kar sakte hain ("small-to-big retrieval" pattern).
- **Why**: Isse dono fayde milte hain — retrieval precise rehta hai (small chunk match) but generation ke time full context milta hai (parent expansion). Ye LlamaIndex/production RAG systems me common battle-tested pattern hai.

**Interview gold line:** "Main ek single chunking strategy sab sources pe force nahi karta — kyunki changelog ka atomic unit ek entry hai, jabki doc ka atomic unit ek section hai. One-size-fits-all chunking production me bahut common mistake hai."

---

## 5. Retrieval System

### Embedding Model Choice

- **Choice**: Domain-tuned or strong general-purpose model — e.g., **OpenAI text-embedding-3-large**, or open-source **BGE-large / E5-large** (agar cost/self-hosting matter kare), fine-tuned lightly on company's own Q&A pairs (tickets) if possible.
- **Why**:
  - High retrieval quality on technical/domain text (API names, error codes).
  - **Fine-tuning on ticket data** helps model understand company-specific jargon (e.g., internal feature names) — general embeddings often miss this.
  - Dimension tradeoff: smaller dims (e.g., 512-768) for cost/speed at scale (500+ tenants = huge index), larger (1536-3072) for quality — mostly hybrid approach: use Matryoshka embeddings (truncatable) if using OpenAI v3.

### Hybrid Search: BM25 + Vector

```
Query → 
  ├── BM25 (keyword/exact match) → Top-K1 candidates
  └── Vector (semantic) → Top-K2 candidates
        → Merge + Dedup → Reciprocal Rank Fusion (RRF) → Combined Top-K
```

### Why Hybrid is Better Than Pure Vector (KEY INTERVIEW POINT)

- **Exact match failure**: Vector search error codes, API endpoint names, version numbers (e.g., "ERR_429", "v2.3.1") ko badly handle karta hai kyunki embeddings semantic similarity pe based hain, exact string match pe nahi.
  - Example: User poochta hai "ERR_TIMEOUT_502" — BM25 ye exact match kar lega, vector search shayad "connection error" wale docs le aaye jo related but not exact hain.
- **Rare terms / acronyms**: Company-specific acronyms (jaise internal product names) jinke liye embedding model ne training me kabhi nahi dekha, BM25 unhe reliably match karta hai.
- **Semantic gaps**: Vice-versa, agar user natural language me poochta hai ("why isn't my data syncing") but doc me "synchronization latency" likha hai — pure BM25 miss karega, vector search ye pakड़ lega.
- **Conclusion**: Hybrid = best of both worlds. Combine via **Reciprocal Rank Fusion (RRF)** ya weighted score fusion.

**Interview line:** "Pure vector search production me aksar surprising failures deta hai jab query me specific identifiers hote hain — error codes, SKU numbers, API names. Isliye har serious RAG system hybrid retrieval use karta hai, sirf vector search nahi."

---

## 6. Reranking Layer

### Why Needed

- Initial retrieval (bi-encoder / BM25) **fast hai but approximate** — query aur document ko independently embed karta hai, unke beech real interaction nahi dekhta.
- **Cross-encoder reranker** query + document dono ko **together** process karta hai (joint attention), jisse relevance scoring bahut zyada accurate hoti hai.
- Result: Top-20 retrieved chunks me se actual best 5 nikalna — precision boost.

### When to Use

- Jab retrieval K bada ho (e.g., top-20) aur unme se sirf top-3-5 hi LLM ko dena hai — reranker ye filtering intelligently karta hai.
- High-stakes domains (B2B support, legal, medical) jaha precision critical hai.

### Tradeoff: Latency vs Quality

| | Without Reranker | With Reranker |
|---|---|---|
| Latency | Faster (~100-200ms saved) | +200-500ms typically |
| Precision@5 | Lower (~70-75%) | Higher (~85-90%+) |
| Hallucination risk | Higher (irrelevant chunks confuse LLM) | Lower |

- **Decision**: For P95 < 3s constraint, reranker latency budget carefully allocate karo. Use a **lightweight, fast cross-encoder** (e.g., Cohere Rerank, bge-reranker-base, not the largest variant) to keep it under ~300ms.
- Agar latency budget tight hai, **reranker sirf tab trigger karo jab retrieval score ambiguous ho** (top results ke beech confidence close hai) — conditional reranking.

---

## 7. Prompt Design (CRITICAL)

### System Prompt Structure

```
You are a customer support assistant for [Company]. 
Answer ONLY using the provided context chunks below. 

RULES:
1. Every factual claim in your answer MUST be followed by a citation 
   marker like [1], [2] referring to the source chunk.
2. If the context does not contain enough information to answer 
   confidently, respond EXACTLY with: 
   "I don't have enough information to answer this confidently. 
   I'm escalating this to a human agent."
3. Do NOT use any knowledge outside the provided context, even if 
   you know the answer from general knowledge.
4. If multiple chunks conflict, mention the most recent one 
   (check timestamps) and note the discrepancy.
5. Keep answers concise, technical, and actionable.

CONTEXT:
[1] (source: docs/webhooks.md, updated: 2026-06-01)
"Webhook retries follow exponential backoff, max 5 attempts..."

[2] (source: changelog v2.3, date: 2026-06-10)
"Fixed webhook retry bug causing duplicate deliveries..."

CONVERSATION HISTORY:
User: Why is my webhook failing?
Assistant: [previous answer]

CURRENT QUESTION:
{user_query}
```

### Citation Generation Prompt Pattern

- Force structured output: answer text with inline `[1]`, `[2]` markers + a separate JSON block mapping citation number → chunk_id/source_url.
- **Post-hoc validation**: After LLM generates, run a quick check — for each citation marker, verify the cited chunk actually contains semantically similar content (using a small similarity check) to catch "fake citations."

### Abstention Prompt Pattern

- Explicit instruction + **few-shot examples** of when to abstain (helps a LOT more than instruction alone):
```
Example: 
Context: [Only about pricing plans]
Question: "How do I reset my API key?"
Answer: "I don't have enough information to answer this confidently. 
I'm escalating this to a human agent."
```

### Preventing Hallucination — Techniques

1. **Closed-book constraint** in prompt ("ONLY use provided context").
2. **Low temperature** (0.0-0.2) for factual support answers.
3. **Citation-forced generation** — answer without citation likely means model straying outside context.
4. **Self-consistency check** (optional, for high-stakes) — generate answer twice, compare.
5. **Retrieval confidence threshold BEFORE generation** — don't even call LLM if retrieval score too low, directly abstain (saves cost too!).

**Interview line:** "Prompt design akela hallucination solve nahi karta — main ise ek layered defense ke roop mein dekhta hoon: retrieval confidence gate → grounded prompt → post-hoc citation validation. Koi bhi ek layer akela reliable nahi hai."

---

## 8. Multi-Tenant Architecture

### Options Comparison

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **Separate DB per tenant** | Har tenant ka apna vector DB instance | Maximum isolation | Not scalable to 500+ tenants — infra overhead insane |
| **Separate Index per tenant** | Same DB, alag-alag index/collection | Good isolation, manageable | Index management overhead grows linearly, resource fragmentation |
| **Shared Index + Namespace/Metadata filtering** | Ek hi index, har vector ke sath `tenant_id` metadata, query time strict filter | Scalable, cost-efficient, easy to manage | Isolation depends on **strict enforcement** — bug hone pe leakage risk |

### What I'd Pick for 500 Tenants

- **Namespace-based isolation** (e.g., Pinecone namespaces, Qdrant collections-per-tenant-group, or metadata filtering in a shared index) — most vector DBs (Pinecone, Weaviate, Qdrant) support native namespace/partition feature.
- **Why**: 500 tenants ke liye separate DB/infra bahut costly aur operationally heavy hoga. Namespace approach **cost-efficient + scalable** hai, aur agar namespace-level isolation native DB feature hai (not just app-level filter), toh security bhi strong rehti hai.
- **For very large tenants (whale customers)**, hybrid approach: bade tenants ko dedicated namespace/shard do, chhote tenants shared shard me (pooled) — **tiered multi-tenancy**.

### Preventing Data Leakage

1. **Mandatory tenant_id filter at query time** — never optional, enforced at the retrieval SDK/query-builder level (not just application logic — bake it into a middleware/wrapper so devs literally cannot query without it).
2. **Row-level security / namespace isolation** at DB level (defense in depth — not just app code).
3. **Separate embedding calls per tenant** — never batch-mix tenant data in same embedding/inference call context.
4. **Automated leakage testing** — CI pipeline test: query tenant A, assert zero results from tenant B's namespace.
5. **Audit logging** — every retrieval logs tenant_id + returned chunk_ids, anomaly detection on cross-tenant access patterns.

**Interview line:** "Multi-tenant RAG me sabse bada risk 'silent' data leakage hai — jaha bug quietly wrong tenant ka data serve kar de. Isliye main isolation ko infra level pe enforce karta hoon, sirf application code trust nahi karta."

---

## 9. Caching Strategy

### Types of Cache

| Cache Type | What it Caches | Placement |
|---|---|---|
| **Exact Query Cache** | Same query (hash) → same answer (with TTL) | Before retrieval — first check |
| **Semantic Cache** | Similar queries (embedding similarity > threshold, e.g., 0.95) → reuse cached answer | Before retrieval, after exact cache miss |
| **Retrieval Cache** | Cache retrieved chunk IDs for common queries | Between retrieval and reranking |
| **Embedding Cache** | Cache embeddings of frequently repeated doc chunks | At ingestion + query embedding step |

### Pipeline Placement

```
Query → [Exact Cache Check] → miss → [Semantic Cache Check] → miss 
      → Retrieval → Rerank → Generation → Cache the result 
      → Return
```

- **TTL management**: Cache TTL should be shorter than data freshness requirement — e.g., if changelog updates daily, cache TTL max few hours, with **active invalidation** on ingestion of new/updated docs (invalidate cache entries linked to updated source_ids).
- **Per-tenant cache namespace** — cache bhi tenant-isolated honi chahiye (same leakage risk applies!).

**Why this matters for cost**: Cost < $0.02/query constraint ke liye caching critical hai — agar 30-40% queries repeat/similar hain (support systems me common — "how do I reset password" jaisa FAQ), cache hit se LLM call hi skip ho jata hai, massive cost saving.

**Interview line:** "Caching sirf latency optimize nahi karta, humare cost constraint ($0.02/query) ko meet karne ka primary lever hai — kyunki LLM call sabse expensive step hai pipeline me."

---

## 10. Feedback Loop

### How Thumbs Up/Down Improves System

1. **Immediate signal capture**: Har response ke sath 👍/👎 + optional free-text reason logged with (query, retrieved_chunks, generated_answer, tenant_id).
2. **👎 triage**:
   - Retrieval problem (right chunks nahi mile) → retrieval quality issue
   - Generation problem (right chunks the, answer galat bana) → prompt/generation issue
   - Stale data → ingestion issue
3. **Weekly/periodic analysis**: Cluster negative feedback by failure type, prioritize fixes.

### Tuning Retrieval from Feedback

- **Hard negative mining**: 👎 responses ke retrieved-but-wrong chunks ko "hard negatives" bana ke reranker/embedding model ko fine-tune karo.
- **Query rewriting improvements**: Agar pattern dikhta hai ki certain query phrasing consistently fail hoti hai, query rewriting prompt update karo.
- **Golden dataset growth**: 👍 (high confidence + positive feedback) query-answer-citation pairs ko **eval golden set** me add karo — regression testing ke liye.
- **Human-in-the-loop correction**: Escalated tickets ka human-resolved answer wapas knowledge base me feed karo (with review) — flywheel complete.

**Interview line:** "Feedback loop RAG system ko static se living system banata hai — main ise as a data flywheel treat karta hoon: production failures → labeled data → retrieval/reranker fine-tuning → better system."

---

## 11. Failure Cases (IMPORTANT FOR INTERVIEW)

### a) Conflicting Documents Retrieved
- **Problem**: Old doc says "max 3 retries", new changelog says "max 5 retries".
- **Solution**: Timestamp-aware ranking (prefer recent), explicit conflict-detection prompt instruction ("if sources conflict, state the most recent and flag the discrepancy"), ideally ingestion pipeline marks old doc as `is_current=false` when superseded.

### b) Cross-Product Queries
- **Problem**: Company has multiple products (e.g., "Analytics" + "Billing" modules), user query spans both ("why isn't my billing data showing in analytics dashboard").
- **Solution**: Query decomposition — break into sub-queries per product area, retrieve separately, merge context. Also tag chunks with `product_area` metadata for smarter routing.

### c) Stale Docs Issue
- Already covered in Section 3 — versioning + `is_current` flag + recency-boosted ranking.

### d) Hallucination Cases
- **Problem**: LLM confidently answers using general knowledge instead of context, or "fills gaps" between chunks incorrectly.
- **Solution**: Closed-book prompting, citation-forced generation, post-hoc citation validation, low temperature, confidence gating before generation.

### e) (Bonus) Ambiguous Query
- **Problem**: "It's not working" — too vague.
- **Solution**: Clarifying question flow — LLM asks follow-up instead of guessing ("Can you tell me which feature isn't working?").

---

## 12. Metrics & Evaluation

### Offline Evaluation

| Metric | What it Measures | How |
|---|---|---|
| **Retrieval Precision@K / Recall@K** | Kya sahi chunks retrieve ho rahe hain | Golden dataset (query → correct chunk_ids) |
| **MRR (Mean Reciprocal Rank)** | Correct chunk kitni jaldi top pe aata hai | Same golden dataset |
| **Faithfulness / Groundedness score** | Answer context se match karta hai ya nahi | LLM-as-judge or NLI-based entailment check |
| **Hallucination rate** | % answers with unsupported claims | LLM-judge comparing answer claims vs retrieved context |
| **Citation accuracy** | Kya cited source actually claim support karta hai | Automated check: citation span vs answer claim overlap |

### Online Evaluation

| Metric | What it Measures |
|---|---|
| **CSAT / thumbs up rate** | User satisfaction |
| **Escalation rate** | % queries going to human (too high = bad retrieval, too low = risky over-confidence) |
| **Resolution rate** | % queries resolved without further follow-up |
| **P95 latency (first token)** | SLA compliance |
| **Cost per query** | Business constraint tracking |
| **Deflection rate** | % tickets fully handled by bot (business KPI) |

### How to Measure Accuracy / Hallucination Rate Practically

- Maintain a **golden eval set** (200-500 curated Q&A pairs with verified answers + correct source chunks) — run this **on every pipeline change** (CI for RAG).
- Use **LLM-as-judge** (a stronger model, e.g., GPT-4/Claude Opus) to score: faithfulness, relevance, completeness — on sampled production traffic weekly.
- Track **escalation rate trend** — sudden spike = something broke upstream (ingestion failure, index corruption).

**Interview line:** "RAG evaluation is not one metric — main retrieval quality aur generation quality dono ko alag-alag measure karta hoon, kyunki agar retrieval fail ho raha hai, generation metrics bhi meaningless honge (garbage in, garbage out)."

---

## 13. Bonus — High-Level Thinking

### a) How to Detect Confidently Wrong Answers?
- **Multi-signal approach** (single confidence score is not enough):
  1. Retrieval score (low similarity = red flag even if LLM sounds confident)
  2. NLI-based entailment check (does context actually entail the generated claim?)
  3. Self-consistency (generate 2-3 times with slight variation, check agreement)
  4. Citation validation (citation exists but doesn't actually support claim = red flag)
- **Key insight**: LLM's linguistic confidence (tone) is NOT a reliable signal — must rely on external/structural checks.

### b) Tenant Data Leakage Debugging Steps
1. Reproduce with test query on affected tenant — check retrieved chunk_ids and their tenant_id metadata.
2. Check query-time filter logic — was tenant_id filter actually applied? (log the exact DB query executed)
3. Check ingestion — was a chunk mistakenly tagged with wrong tenant_id during ingestion?
4. Check cache layer — was cached response served from wrong tenant's cache namespace?
5. Audit recent deploys — did a code change bypass the middleware-enforced filter?
6. Add regression test for this exact case going forward.

### c) Reranker adds 400ms latency, improves quality by 8% — Ship or Not? (Decision Framework)
- **Framework, not a yes/no answer** (say this in interview!):
  1. Check current latency budget: P95 < 3s — kitna headroom hai? Agar retrieval+generation already 2.5s le raha hai, 400ms add nahi kar sakte.
  2. What does "8% quality improvement" mean — precision? user satisfaction? If it reduces hallucination/escalation meaningfully, worth it.
  3. **A/B test in production** — don't decide on offline metrics alone. Measure actual CSAT/resolution rate impact.
  4. **Conditional/selective reranking** — only rerank when top retrieval scores are ambiguous (close together) — gets most of the quality gain with a fraction of the latency cost.
  5. **Optimize instead of binary decision** — smaller/faster reranker model, or run reranking in parallel with something else, or cache reranked results for repeat queries.
- **My answer**: "I'd ship it behind a flag, A/B test with real users measuring resolution rate + latency P95, and use conditional reranking to control cost/latency — not a blanket yes/no."

### d) Scaling from 500 → 50,000 Tenants
1. **Namespace/shared-index approach breaks down at some point** — move to **sharded architecture**: multiple vector DB clusters, tenants hashed/routed to shards (consistent hashing).
2. **Tiered infrastructure**: large/enterprise tenants get dedicated shards, small tenants pooled (multi-tenant shard) — cost-efficient.
3. **Ingestion pipeline**: move from per-tenant sync jobs to **event-driven, queue-based** (Kafka/SQS) architecture to handle ingestion volume without blocking.
4. **Caching becomes more critical** — semantic cache hit rate directly reduces infra load at this scale.
5. **Embedding cost optimization**: batch embedding jobs, smaller embedding models for less critical tenants, or self-hosted models to control per-query cost at scale.
6. **Observability**: per-tenant latency/cost/error dashboards essential — noisy-neighbor problem (one tenant's heavy usage affecting others) must be handled with rate limiting/quotas.
7. **Index maintenance**: automated re-indexing, compaction jobs, since index size grows massively.

### e) Explainability: Map Answer Sentence → Source Sentence
- **Approach**:
  1. Generate answer with explicit citation markers per sentence/claim (`[1]`, `[2]`) — enforced via prompt.
  2. **Sentence-level attribution model** (optional advanced): after generation, run each answer sentence through an NLI/entailment model against each cited chunk to get a fine-grained "this exact sentence is supported by this exact source sentence" mapping.
  3. UI-level: highlight-on-hover — user hovers over answer sentence, source sentence highlights in the doc panel (like Perplexity.ai's UI pattern).
  4. This builds **user trust** — critical for enterprise B2B customers who need to verify before acting on the answer.

---

## Quick Interview Cheat-Sheet (Say These Lines Confidently)

- "Hybrid retrieval kyunki B2B support queries me exact identifiers (error codes, API names) common hain jo pure vector search miss karta hai."
- "Chunking strategy source-dependent honi chahiye — one-size-fits-all ek common production mistake hai."
- "Confidence gating retrieval-time pe hi hona chahiye, generation ke baad nahi — cost aur hallucination dono save karta hai."
- "Multi-tenancy isolation ko infra-level enforce karta hoon, app-code trust nahi karta — leakage 'silent' bug hoti hai."
- "Caching sirf latency nahi, humara primary cost-control lever hai given the $0.02/query constraint."
- "Reranker ship karne ka decision ek framework hai — latency budget, A/B test data, aur conditional triggering pe depend karta hai, blanket yes/no nahi."
- "RAG evaluation retrieval aur generation quality ko alag measure karta hai — dono independent failure points hain."

---
