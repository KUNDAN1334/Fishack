# Fishly — developer entrypoints.
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

test:
	pytest -q

# Phase 4 will wire this to the real harness: python -m fishnet.run
eval:
	@echo "fishnet eval harness arrives in Phase 4 (python -m fishnet.run)"
