"""Central configuration for Fishly.

Implements the project rule: every constant, threshold, and model name lives
HERE with a comment explaining how it was chosen — never inline in code.
Model names are config (not code) because free-tier lineups change monthly.

Settings are read from environment variables / .env via pydantic-settings.
Env var names match field names case-insensitively (DATABASE_URL -> database_url).
"""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):
    """USD per 1M tokens. Used for VIRTUAL cost tracking (see budget.py)."""

    input_per_million: float
    output_per_million: float


# --------------------------------------------------------------------------
# Virtual cost table — methodology:
# We use free tiers, so real spend is $0. But "cost per query" is a core
# production metric (Design.md §12), so we track what each call WOULD cost:
# for each model we use, take the paid-tier price of the same model (or the
# closest comparable hosted model). Snapshot: July 2026 public price pages.
# PRODUCTION NOTE: with paid APIs this table disappears — cost comes from
# actual usage on the provider invoice; the tracking code stays identical.
# --------------------------------------------------------------------------
VIRTUAL_PRICES: dict[str, ModelPrice] = {
    # Groq paid-tier prices for the same models
    "llama-3.1-8b-instant": ModelPrice(input_per_million=0.05, output_per_million=0.08),
    "llama-3.3-70b-versatile": ModelPrice(input_per_million=0.59, output_per_million=0.79),
    "qwen/qwen3-32b": ModelPrice(input_per_million=0.29, output_per_million=0.59),
    # Google paid-tier Gemini Flash
    "gemini-2.5-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    # OpenRouter :free -> price of the same model on paid routes
    "meta-llama/llama-3.3-70b-instruct:free": ModelPrice(input_per_million=0.59, output_per_million=0.79),
    # Ollama is local ($0 marginal) — virtual price = comparable hosted 8B
    "llama3.1:8b": ModelPrice(input_per_million=0.05, output_per_million=0.08),
}

# Conservative mid-range fallback when a model isn't in the table, so cost
# numbers are never silently zero for unknown models.
DEFAULT_VIRTUAL_PRICE = ModelPrice(input_per_million=0.50, output_per_million=1.50)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ------------------------------------------------------------- infra --
    database_url: str = "postgresql://fishly:fishly@localhost:5432/fishly"
    redis_url: str = "redis://localhost:6379/0"

    # ------------------------------------------------- LLM provider chain --
    # Order matters: first configured provider is primary, the rest are
    # failover targets (Design-doc framing: multi-provider resilience).
    # Groq first because it has the fastest inference and the most generous
    # free request quota; Ollama last because it's optional and slowest.
    llm_provider_order: str = "groq,gemini,openrouter,ollama"

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1:8b"

    # -------------------------------------------------------- generation --
    # 0.1: Design.md §7 prescribes 0.0-0.2 for factual support answers.
    # Not 0.0 because a tiny bit of sampling avoids degenerate repetition on
    # some open models while staying effectively deterministic.
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    # Generous timeout: free tiers queue under load; better to wait than to
    # burn a failover on a slow-but-healthy provider.
    llm_timeout_seconds: float = 60.0

    # ----------------------------------------------------------- retries --
    # 3 attempts w/ exponential backoff (1s, 2s, 4s + jitter) before failing
    # over. More attempts = better odds on a rate-limited provider but worse
    # worst-case latency; 3 is the conventional sweet spot.
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 20.0

    # -------------------------------------------------------- embeddings --
    # bge-small: 384 dims, strong MTEB score for its size, fast on CPU.
    # The DB schema hardcodes vector(384) — changing this requires a
    # migration AND full re-ingestion (embeddings from different models are
    # not comparable). See ADR-005.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # --------------------------------------------------------- retrieval --
    # Design.md §5: each leg proposes candidates, RRF merges them to top-20.
    # Per-leg limit == fusion limit is deliberate: asking a leg for MORE than
    # we will keep costs almost nothing (both indexes are already sorted) and
    # gives RRF room to promote a chunk that leg A ranked 18th but leg B
    # ranked 2nd — which is exactly the agreement signal hybrid exists for.
    retrieval_candidates_per_leg: int = 20
    retrieval_fusion_top_k: int = 20

    # Design.md §6: top-5 chunks go to the LLM. More context is not free —
    # it costs tokens, latency, and "needle in a haystack" dilution (§4).
    rerank_top_k: int = 5

    # RRF constant from Cormack et al. 2009 ("Reciprocal Rank Fusion
    # Outperforms Condorcet"). k damps the gap between adjacent ranks:
    # at k=60, rank 1 scores 1/61 and rank 2 scores 1/62 — nearly equal, so
    # no single leg can dominate on one confident hit. Smaller k = more
    # top-heavy; larger k = flatter/more democratic.
    rrf_k: float = 60.0
    # Equal weights by default. Weighting reintroduces exactly the per-corpus
    # tuning burden RRF was chosen to avoid (ADR-011) — Phase 4 may tune
    # these against the golden set, with evidence.
    rrf_weight_bm25: float = 1.0
    rrf_weight_vector: float = 1.0

    # HNSW beam width at query time. pgvector's default is 40, which is too
    # small once a selective `tenant_id` filter discards most of the beam —
    # the filtered-ANN problem documented in 001_init.sql and interview_prep
    # Q6. 100 costs a few ms at our scale and materially protects recall.
    hnsw_ef_search: int = 100

    # ---------------------------------------------------------- reranker --
    # bge-reranker-base: cross-encoder, ~280MB, CPU-viable. Design.md §6
    # explicitly says use a lightweight variant, not the largest.
    # PRODUCTION NOTE: a paid setup would use Cohere Rerank (hosted, no local
    # compute, already-normalized scores) or bge-reranker-large on GPU.
    reranker_model_name: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = True
    # 16 pairs per batch: modest CPU memory, still amortizes per-batch cost.
    reranker_batch_size: int = 16
    # Cross-encoder input is query + chunk together. 512 is the model's own
    # limit; our chunks average ~200 tokens so this rarely binds, but silent
    # truncation here would corrupt scores, so we set it explicitly and log.
    reranker_max_length: int = 512

    # ---------------------------------------- conditional reranking (§13c) --
    # OFF by default in Phase 2 on purpose: always-reranking is the quality
    # CEILING, and Phase 4 needs that ceiling as a baseline to measure what
    # conditional reranking actually costs in recall. Flip to true to trade
    # quality for latency. See ADR-014.
    conditional_rerank_enabled: bool = False
    # "Ambiguous" = the top RRF score is not clearly ahead of the Nth.
    # Window of 5 matches rerank_top_k: we care whether the set we would ship
    # unreranked is already well-ordered.
    rerank_ambiguity_window: int = 5
    # Relative margin (s1 - sN) / s1 over FUSED scores.
    #
    # MEASURED, not guessed. 0.30 was the initial guess and it is wrong by
    # roughly 4x. Two real queries against the acme corpus both produced a
    # margin of 0.076, and the arithmetic explains why: when all 5 top
    # candidates are found by BOTH legs (13/20 overlap is typical here), the
    # scores are 2/(k+1)...2/(k+5), whose margin is bounded at 0.062. The
    # margin only gets large when a top-5 candidate was found by just ONE leg
    # — a single-leg chunk at rank 5 scores 1/65 instead of 2/65, pushing the
    # margin to 0.53.
    #
    # So this knob is really asking: "was the top-5 unanimous?" At 0.30 the
    # gate would essentially never skip, which is a config that LOOKS tuned
    # and does nothing. 0.10 sits just above the all-agree ceiling.
    #
    # HONEST STATUS: four real queries through the playground produced margins
    # of 0.055, 0.059, 0.076, 0.076. At 0.10 the gate STILL never fires on any
    # of them. So conditional reranking is implemented and tested but NOT yet
    # demonstrated to do anything on this corpus — do not describe it as a
    # working latency optimization until Phase 4 says so.
    #
    # The open question Phase 4 must answer is not just "what threshold" but
    # "is the RRF margin a usable ambiguity signal at all?" RRF compresses
    # scores hard by design (that is what k=60 is for), so the dynamic range
    # available to threshold on may simply be too narrow. If the sweep over
    # 0.03-0.15 shows no threshold that trades latency for acceptable recall,
    # the alternative is to gate on the top RAW leg scores instead — at the
    # cost of the cross-query comparability that made fused scores attractive.
    rerank_margin_threshold: float = 0.10

    @property
    def provider_order(self) -> list[str]:
        """Parsed fallback chain, e.g. ['groq', 'gemini', 'openrouter']."""
        return [p.strip() for p in self.llm_provider_order.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor so every module shares one Settings instance.

    lru_cache means the .env file is read once per process; tests can call
    get_settings.cache_clear() to re-read after monkeypatching env vars.
    """
    return Settings()
