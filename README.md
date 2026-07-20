# Fishly 🎣

**Fishly fishes out the exact answer from a sea of docs — no fishy answers: every claim is cited, verified, and confidence-gated; when Fishly isn't sure, it escalates to a human instead of hallucinating.**

A multi-tenant RAG customer support assistant for "Flowlytics" (a fictional B2B analytics + billing SaaS). Built raw — no LangChain/LlamaIndex — on FastAPI, Postgres + pgvector, Redis, local embedding/reranker models, and free-tier LLM APIs with an automatic multi-provider fallback chain.

> **Status: Phase 0 complete** — infra, config, DB schema, provider-agnostic LLM client.
> This README gets its architecture diagram, results tables, and demo GIF in Phase 7.

## Quickstart (3 commands)

```bash
cp .env.example .env        # then add your free Groq / Gemini / OpenRouter keys
docker compose up -d --build && python scripts/migrate.py
python scripts/smoke_test.py
```

Dev loop: `make infra` + `make api` (local uvicorn with reload), `make test`.

## Docs

- `Design.md` — the system design this implements
- `docs/walkthroughs/` — per-phase build walkthroughs
- `docs/decisions.md` — ADR log · `docs/interview_prep.md` — Q&A · `docs/glossary.md`
