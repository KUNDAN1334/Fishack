"""Content hashing and the embedding cache key.

Dedup correctness decides whether re-ingestion is a cheap no-op or a source
of duplicate chunks — duplicates would corrupt retrieval (the same text
occupying multiple top-K slots) and inflate recall metrics.
"""

from app.ingestion.dedup import content_hash, embedding_cache_key, normalize


def test_normalize_is_stable_across_line_endings():
    assert normalize("a\r\nb") == normalize("a\nb")


def test_normalize_strips_trailing_whitespace_and_blank_edges():
    assert normalize("\n\n  hello   \n\n") == "hello"
    assert normalize("line   \nnext\t") == "line\nnext"


def test_cosmetic_changes_do_not_change_the_hash():
    """Otherwise every re-crawl would re-embed the whole corpus."""
    assert content_hash("Retry limit is 3.\n") == content_hash("Retry limit is 3.  \r\n\r\n")


def test_real_content_change_changes_the_hash():
    assert content_hash("Retry limit is 3.") != content_hash("Retry limit is 5.")


def test_case_change_is_a_real_change():
    """ERR_TIMEOUT_502 vs err_timeout_502 are genuinely different identifiers
    in a support corpus — normalization must not lowercase."""
    assert content_hash("ERR_TIMEOUT_502") != content_hash("err_timeout_502")


def test_hash_is_full_length_sha256():
    assert len(content_hash("x")) == 64


def test_embedding_key_depends_on_model():
    """A model switch must MISS the cache, never return vectors from the
    wrong embedding space (ADR-005)."""
    text = "Webhook retries use exponential backoff."
    assert embedding_cache_key("BAAI/bge-small-en-v1.5", text) != \
           embedding_cache_key("BAAI/bge-base-en-v1.5", text)


def test_embedding_key_is_stable_for_same_model_and_text():
    text = "Webhook retries use exponential backoff."
    assert embedding_cache_key("m", text) == embedding_cache_key("m", text + "  ")


def test_embedding_key_separator_prevents_collision():
    """Without a separator, ('ab','c') and ('a','bc') would collide."""
    assert embedding_cache_key("ab", "c") != embedding_cache_key("a", "bc")
