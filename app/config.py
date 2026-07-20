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
