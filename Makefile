# Fishack — developer entrypoints.
# On Windows without make: each target is 1-2 commands you can run directly
# (docker compose ..., python -m ...). See README quickstart.

.PHONY: up down logs migrate smoke api test eval

# Start infra (postgres+pgvector, redis) and the API container
up:
	docker compose up -d --build

# Infra only — use this during development when running the API locally
infra:
	docker compose up -d postgres redis

down:
	docker compose down

logs:
	docker compose logs -f

# Apply SQL migrations in app/db/migrations/ in filename order
migrate:
	python scripts/migrate.py

# Verify postgres+pgvector, redis, and every configured LLM provider
smoke:
	python scripts/smoke_test.py

# Generate the synthetic Flowlytics corpus into data/raw/ (cached; --offline
# works with no API keys)
corpus:
	python scripts/generate_corpus.py

# Load the corpus into Postgres: chunk, embed, version
ingest:
	python scripts/ingest.py run

# Chunk counts and token distribution per tenant/source
ingest-stats:
	python scripts/ingest.py stats

# Run the API locally with reload (faster dev loop than the docker image)
api:
	uvicorn app.main:app --reload --port 8000

# Side-by-side BM25 / vector / hybrid / reranked for any query (Phase 2)
playground:
	python scripts/retrieval_playground.py --tenant acme

# Full chat pipeline with every stage's decision visible (Phase 3)
chat:
	python scripts/chat_playground.py --tenant acme

# Print the exact messages the model receives for a query — the fastest way to
# answer "why did it say that?"
show-prompt:
	python scripts/chat_playground.py --tenant acme --show-prompt --query "webhook retry limit"

# Classify thumbs-down feedback into retrieval / generation / stale-data
triage:
	python scripts/triage_feedback.py

# Turn thumbs-up answers into golden-set candidates for review
golden-candidates:
	python scripts/triage_feedback.py --golden-candidates

# Operational metrics (needs the API running: make api)
stats:
	curl -s http://localhost:8000/admin/stats | python -m json.tool

test:
	pytest -q

# Pure tests only — no Postgres needed (integration tests skip themselves,
# this just makes the intent explicit and the run faster)
test-unit:
	pytest -q -m "not integration"

# The isolation test on its own. Run this before every commit that touches
# retrieval; it is the check that a leak cannot ship (Design.md §8).
test-isolation:
	pytest -q tests/test_tenant_isolation.py tests/test_tenant_scope.py

# Full eval: retrieval metrics + LLM-as-judge + hard assertions, compared
# against the committed baseline. Exit code 1 on a regression.
eval:
	python -m fishnet.run

# Retrieval metrics only — no LLM calls, no cross-encoder, so it runs
# regardless of quota and finishes in under a minute. This is the one to run
# while iterating on retrieval, and it produces the BM25-vs-vector-vs-hybrid
# comparison table.
eval-retrieval:
	python -m fishnet.run --retrieval-only --arms hybrid,bm25,vector

# The with/without-reranker axis (Design.md §6). Slow — the cross-encoder is
# ~5s per case on CPU — so it is a separate target you run deliberately.
eval-rerank:
	python -m fishnet.run --retrieval-only --arms hybrid,hybrid+rerank

# Ten cases, full pipeline. The development loop.
eval-smoke:
	python -m fishnet.run --sample 10

# Regenerate the golden set from the corpus spec (prompts before overwriting).
golden:
	python scripts/build_golden_set.py

# Record the current scorecard as the committed baseline. Review the diff.
baseline:
	python -m fishnet.run --write-baseline

# The naive-vs-per-source chunking experiment (Design.md §4).
chunking-experiment:
	python scripts/chunking_experiment.py ingest
	python scripts/chunking_experiment.py compare

# Sweep the confidence gate against the golden set. No LLM calls.
tune:
	python scripts/tune_thresholds.py
