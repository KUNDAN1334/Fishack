# Fishly 🎣

**Fishly fishes out the exact answer from a sea of docs — no fishy answers: every claim is cited, verified, and confidence-gated; when Fishly isn't sure, it escalates to a human instead of hallucinating.**

A multi-tenant RAG customer support assistant for "Flowlytics" (a fictional B2B analytics + billing SaaS). Built raw — no LangChain/LlamaIndex — on FastAPI, Postgres + pgvector, Redis, local embedding/reranker models, and free-tier LLM APIs with an automatic multi-provider fallback chain.

> **Status: Phase 1 complete** — infrastructure, LLM client, synthetic corpus, and the full ingestion pipeline.
> Results tables, architecture diagram and demo GIF land in Phase 7.

## Quickstart

```bash
cp .env.example .env                  # add free Groq / Gemini / OpenRouter keys
docker compose up -d --build          # postgres+pgvector, redis
pip install -e ".[dev]"               # includes sentence-transformers (~2GB torch, one time)
python scripts/migrate.py             # apply the schema
python scripts/smoke_test.py          # verify infra + every configured provider
```

Then build the knowledge base:

```bash
python scripts/generate_corpus.py     # synthetic Flowlytics corpus -> data/raw/
python scripts/ingest.py run          # chunk, embed, version (first run downloads bge-small)
python scripts/ingest.py stats        # what landed
```

`make` targets exist for all of these (`make up`, `make migrate`, `make corpus`, `make ingest`, `make test`).

## What exists today

**Phase 0 — infrastructure**

- docker-compose: Postgres 16 + pgvector, Redis, API, optional Ollama profile
- Config system with every threshold and model name commented (`app/config.py`)
- Full DB schema in raw SQL migrations: tenants, documents, chunks, embedding cache, traces, escalations, feedback
- Provider-agnostic LLM client over raw `httpx`: Groq → Gemini → OpenRouter → Ollama fallback chain, exponential backoff with jitter, `Retry-After` handling, streaming (SSE parsed by hand), per-provider Redis budget counters with virtual-cost tracking

**Phase 1 — corpus + ingestion**

- Synthetic Flowlytics corpus: 60 doc pages, 40 changelog entries, 50 resolved tickets across two tenants (`acme`, `globex`), generated from a deterministic skeleton with LLM-written prose (cached, reproducible, works offline)
- Deliberately planted stale data: one clean supersession + four unmarked doc/changelog conflicts
- Three chunking strategies, one per source type (structure-aware / entry-level / Q&A pair)
- Content-hash dedup, versioning with soft-delete, changelog-driven supersession, conflict tagging
- Local bge-small embeddings on CPU, cached by `sha256(model + text)` so nothing is ever embedded twice
- Ingest + inspect CLI (`scripts/ingest.py run | stats | inspect | conflicts | reset`)

**Tests:** 67 passing — fallback chain, backoff math, budget counters, chunker edge cases (tables, code fences, tiny docs, walls of text, overlap, model-limit cap), dedup, loaders.

## Coming next

Phase 2 hybrid retrieval (BM25 + vector + RRF + cross-encoder reranker) · Phase 3 query rewriting, confidence gate, grounded generation with citation validation · Phase 4 `fishnet/` eval harness + golden set + the chunking before/after experiment · Phase 5 caching, feedback loop, `/stats` · Phase 6 Next.js frontend · Phase 7 documentation and results.

## Docs

| File | Contents |
|---|---|
| `Design.md` | The system design this implements |
| `docs/architecture.md` | System overview, mermaid diagrams, storage layout |
| `docs/decisions.md` | ADR log — every significant choice, alternatives, why rejected |
| `docs/walkthroughs/` | Per-phase build walkthroughs with file-by-file traces |
| `docs/interview_prep.md` | Accumulated Q&A with model answers |
| `docs/glossary.md` | Every AI term used, in plain sentences |
