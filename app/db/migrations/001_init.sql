-- 001_init.sql — Fishack core schema (Phase 0).
-- Implements Design.md §3 (versioning), §4 (chunk metadata), §8 (tenant
-- isolation), §12 (observability). Later phases ADD tables/columns; this
-- shape is stable.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id          TEXT PRIMARY KEY,           -- 'acme', 'globex'
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Design.md §3: "stale data hallucination ka root cause almost hamesha
-- missing/wrong metadata hota hai" — versioning discipline is enforced at
-- ingestion time, in this table, not patched at generation time.
CREATE TABLE documents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      TEXT NOT NULL REFERENCES tenants(id),
    source_type    TEXT NOT NULL CHECK (source_type IN ('docs', 'changelog', 'ticket')),
    title          TEXT NOT NULL,
    source_path    TEXT NOT NULL,           -- provenance: data/raw/acme/docs/webhooks.md
    doc_version    TEXT,                    -- 'v2.3' for docs/changelogs, NULL for tickets
    effective_date DATE NOT NULL,           -- when this content became true
    is_current     BOOLEAN NOT NULL DEFAULT true,  -- flipped false when superseded
    product_area   TEXT,                    -- 'analytics' | 'billing' (Design.md §11b)
    content_hash   TEXT NOT NULL,           -- sha256 of raw content; dedup on re-ingest
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Same content re-ingested for the same tenant is a no-op. Scoped per
    -- tenant on purpose: acme and globex may legitimately have identical
    -- shared docs, each needing its own row (and its own chunks).
    UNIQUE (tenant_id, content_hash)
);

CREATE TABLE chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    -- Denormalized from documents on purpose: EVERY retrieval query filters
    -- by tenant_id (Design.md §8) and must not need a join to do it. The
    -- leakage test asserts directly against this column.
    tenant_id     TEXT NOT NULL REFERENCES tenants(id),
    chunk_index   INT  NOT NULL,            -- position within the document
    -- NOTE (ADR-004): for docs chunks, content BEGINS with the heading path
    -- ("Webhooks > Retry Logic\n\n..."). Both tsv and embedding therefore
    -- include the heading context. heading_path below is kept separately for
    -- display so the UI can show clean body text.
    content       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,            -- chunk-level dedup + cache keys
    heading_path  TEXT,                     -- 'Webhooks > Retry Logic' (docs only)
    token_count   INT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}',  -- source-specific: version, resolution_tag...
    is_current    BOOLEAN NOT NULL DEFAULT true,
    -- 384 dims = BAAI/bge-small-en-v1.5. Changing models means a migration +
    -- full re-ingest: embeddings from different models are not comparable
    -- (ADR-005).
    embedding     vector(384),
    -- Generated column: the FTS index can never drift out of sync with
    -- content — you cannot update one without the other.
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Re-ingesting a document must replace its chunks, never duplicate them.
    -- Also catches chunker bugs that emit the same index twice.
    UNIQUE (document_id, chunk_index)
);

-- Composite index: every retrieval query starts WHERE tenant_id = $1 AND is_current
CREATE INDEX chunks_tenant_current_idx ON chunks (tenant_id, is_current);

-- BM25-side index (Postgres FTS; see ADR-001 for the ts_rank-vs-true-BM25 nuance)
CREATE INDEX chunks_tsv_idx ON chunks USING GIN (tsv);

-- Vector index for cosine similarity.
-- PRODUCTION NOTE (filtered ANN): HNSW searches the graph FIRST, then
-- Postgres applies the tenant_id/is_current filter to whatever the graph
-- returned. With a selective filter (1 tenant among many) most of the
-- ef_search candidates get discarded and you can receive FEWER than K rows —
-- silently hurting recall. Mitigations, in order of seriousness:
--   1. Raise hnsw.ef_search (default 40) at query time:
--        SET LOCAL hnsw.ef_search = 100;  -- more candidates survive the filter
--   2. pgvector >= 0.8 iterative index scans: keeps walking the graph until
--      enough rows pass the filter.
--   3. Partial index per hot tenant, or partition chunks BY tenant —
--      the "namespace per tenant" pattern from Design.md §8.
--   4. Dedicated vector DBs (Pinecone/Qdrant) implement native filtered
--      HNSW, which is exactly why namespaces are first-class there.
-- At our scale (2 tenants, ~1-2k chunks) ef_search covers it; the
-- retrieval layer (Phase 2) sets it per-query. Full discussion in
-- docs/interview_prep.md.
CREATE INDEX chunks_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- Embeddings are deterministic: same model + same text => same vector.
-- Never compute twice (used for both chunk and query embeddings).
CREATE TABLE embedding_cache (
    cache_key   TEXT PRIMARY KEY,           -- sha256(model_name || text)
    model       TEXT NOT NULL,
    embedding   vector(384) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per request — the observability backbone (Design.md §12).
-- Written from Phase 3 onward; /stats (Phase 5) aggregates over it.
CREATE TABLE traces (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           TEXT REFERENCES tenants(id),
    -- Groups multi-turn conversations. NULLable: single-shot queries and
    -- internal calls (evals, smoke tests) have no conversation. The client
    -- generates and resends it; the server stays stateless (ADR-003).
    conversation_id     UUID,
    query               TEXT NOT NULL,
    rewritten_query     TEXT,               -- after multi-turn resolution (Phase 3)
    action              TEXT CHECK (action IN ('answered', 'abstained', 'escalated', 'cache_hit')),
    answer              TEXT,
    confidence          REAL,               -- top reranker score at gate time
    retrieved_chunk_ids UUID[],
    citation_report     JSONB,              -- post-hoc citation validation (Phase 3)
    provider            TEXT,               -- who actually answered, after failovers
    model               TEXT,
    failover_events     JSONB NOT NULL DEFAULT '[]',
    tokens_in           INT,
    tokens_out          INT,
    virtual_cost_usd    NUMERIC(10, 6),     -- what this WOULD cost at paid-API prices
    cache_status        TEXT,               -- 'miss' | 'exact_hit' | 'semantic_hit'
    retrieval_ms        INT,
    rerank_ms           INT,
    generation_ms       INT,
    total_ms            INT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX traces_tenant_created_idx ON traces (tenant_id, created_at DESC);
CREATE INDEX traces_conversation_idx ON traces (conversation_id) WHERE conversation_id IS NOT NULL;

-- Abstain path (Design.md §2 branch A): full context preserved so a human
-- agent picks up exactly where the bot stopped.
CREATE TABLE escalations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     TEXT NOT NULL REFERENCES tenants(id),
    trace_id      UUID REFERENCES traces(id),
    query         TEXT NOT NULL,
    chat_history  JSONB,
    context       JSONB,                    -- retrieved chunks + scores at abstain time
    reason        TEXT NOT NULL,            -- 'low_confidence' | 'user_requested' | 'conflict'
    status        TEXT NOT NULL DEFAULT 'open',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Design.md §10: the data flywheel starts here.
CREATE TABLE feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    trace_id    UUID NOT NULL REFERENCES traces(id),
    rating      SMALLINT NOT NULL CHECK (rating IN (-1, 1)),  -- thumbs down / up
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- PRODUCTION NOTE: real defense-in-depth would ALSO enable Postgres
-- row-level security (RLS) on chunks/traces/escalations/feedback with a
-- per-request `SET app.tenant_id`, so even raw SQL can't cross tenants.
-- We enforce isolation in the query-builder layer (Phase 2) + the CI
-- leakage test; RLS is the next layer a real team would add.
