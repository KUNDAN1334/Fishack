"""Config parsing: chain order, env overrides, defaults."""

from app.config import Settings


def test_provider_order_parsing():
    s = Settings(llm_provider_order=" groq, gemini ,openrouter ")
    assert s.provider_order == ["groq", "gemini", "openrouter"]


def test_defaults_are_sane():
    s = Settings()
    assert s.embedding_dim == 384  # must match vector(384) in 001_init.sql
    assert 0.0 <= s.llm_temperature <= 0.2  # Design.md §7 range
    assert s.retry_max_attempts >= 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "some-new-model")
    s = Settings()
    assert s.groq_model == "some-new-model"
