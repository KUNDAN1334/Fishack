/**
 * Types mirroring the backend's Pydantic models.
 *
 * Hand-written rather than generated from the OpenAPI schema. At this size a
 * generator is more machinery than it saves, and writing them by hand forces
 * a decision about what the UI actually needs — the backend's ChatResponse
 * has ~25 fields and the UI uses about half.
 *
 * PRODUCTION NOTE: past a handful of endpoints, generate these from
 * /openapi.json in CI. A hand-written type that silently drifts from the API
 * is worse than no type, because TypeScript will confidently vouch for it.
 */

/** One numbered source offered to the model. Mirrors `Citation`. */
export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  title: string;
  source_type: "docs" | "changelog" | "ticket" | string;
  source_path: string;
  heading_path: string | null;
  doc_version: string | null;
  effective_date: string | null;
  score: number;
  /** Ingestion flagged this chunk as contradicted by a newer changelog entry. */
  is_contested: boolean;
  /** Did the answer actually cite it? Set by post-hoc validation. */
  was_cited: boolean;
}

/** One sentence of the answer, checked against the source it cited. */
export interface ClaimCheck {
  claim: string;
  cited_indices: number[];
  similarity: number | null;
  supported: boolean;
  problem: string | null;
}

export interface CitationReport {
  claims: ClaimCheck[];
  /** Markers pointing at sources that were never offered — outright fabrication. */
  invalid_indices: number[];
  unused_indices: number[];
}

/** Why the pipeline did or did not call the model. */
export interface GateDecision {
  should_generate: boolean;
  reason: string;
  top_score: number;
  threshold: number;
  /** 'rerank' | 'fused' | 'none' — the scales differ ~30x, so this is required to read top_score. */
  score_kind: string;
}

export interface RewriteResult {
  original: string;
  rewritten: string;
  changed: boolean;
  skipped_reason: string | null;
  elapsed_ms: number;
}

export type Action = "answered" | "abstained" | "escalated" | "cache_hit";

/** The final SSE event's payload. */
export interface ChatResponse {
  answer: string;
  action: Action;
  tenant_id: string;
  conversation_id: string | null;
  trace_id: string | null;
  citations: Citation[];
  citation_report: CitationReport | null;
  gate: GateDecision | null;
  rewrite: RewriteResult | null;
  escalation_id: string | null;
  confidence: number;
  cache_status: string;
  cache_similarity: number | null;
  provider: string | null;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  virtual_cost_usd: number;
  rewrite_ms: number;
  retrieval_ms: number;
  rerank_ms: number;
  generation_ms: number;
  validation_ms: number;
  total_ms: number;
  degraded_legs: string[];
}

/** What arrives on the `meta` event, before any text. */
export interface ChatMeta {
  citations?: Citation[];
  gate?: GateDecision | null;
  rewrite?: RewriteResult | null;
  escalated?: boolean;
  cache_status?: string;
  cache_similarity?: number | null;
}

/** A rendered turn. `pending` drives the typing indicator. */
export interface Turn {
  role: "user" | "assistant";
  content: string;
  meta?: ChatMeta;
  response?: ChatResponse;
  pending?: boolean;
  error?: string;
  /** Local echo of the feedback the user gave, so the buttons stay lit. */
  rating?: 1 | -1;
}

/** GET /admin/stats. Loosely typed where the shape is a free-form map. */
export interface Stats {
  window: { hours: number; since: string; tenant_id: string | null };
  requests: {
    total: number;
    escalation_rate: number;
    cache_hit_rate: number;
    by_action: Record<string, number>;
  };
  latency_ms: {
    p50: number;
    p95: number;
    mean_retrieval: number;
    mean_rerank: number;
    mean_generation: number;
  };
  cost: {
    methodology: string;
    total_usd: number;
    per_query_usd: number;
    tokens_in: number;
    tokens_out: number;
  };
  quality: {
    thumbs_up: number;
    thumbs_down: number;
    satisfaction_rate: number;
    answers_with_fabricated_citations: number;
    mean_confidence: number;
  };
  escalations: { open: number; by_reason: Record<string, number> };
  by_tenant: {
    tenant_id: string;
    requests: number;
    escalation_rate: number;
    cache_hit_rate: number;
    cost_usd: number;
    p95_ms: number;
  }[];
  providers: Record<string, Record<string, number> | string>;
}
