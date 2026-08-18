"""The answer cache (Design.md §9).

Runs against fakeredis, so no Docker and no network. The behaviours under test
are all correctness rather than speed — a cache that is fast and occasionally
wrong is worse than no cache, because the wrongness is invisible and durable.

Three properties matter most, and each has its own section:

  * tenant isolation — a cache is another place tenant data lives
  * staleness — invalidation must actually evict
  * the identifier guard — the semantic cache's one genuinely dangerous edge
"""

from __future__ import annotations

import datetime as dt

import fakeredis.aioredis
import pytest

from app.cache import keys as cache_keys
from app.cache.models import CachedAnswer
from app.cache.store import AnswerCache, cosine_similarity


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def cache(redis):
    return AnswerCache(redis, ttl_seconds=60, semantic_threshold=0.95)


def answer(text="Retries cap at five attempts [1].", chunk_ids=("c1",), query="q") -> CachedAnswer:
    return CachedAnswer(
        query=query, answer=text, chunk_ids=list(chunk_ids), confidence=0.9,
        provider="groq", model="llama-3.1-8b-instant",
    )


def vector(*values) -> list[float]:
    """A unit vector, so cosine similarity is the dot product."""
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


# --------------------------------------------------------- exact cache --


async def test_exact_hit_returns_the_stored_answer(cache):
    await cache.store("acme", "what is the retry limit?", answer())
    hit = await cache.get_exact("acme", "what is the retry limit?")
    assert hit is not None and "five attempts" in hit.answer


async def test_exact_cache_normalizes_case_and_whitespace(cache):
    """Trivial variation is the same question. Anything more than case and
    whitespace is deliberately NOT folded — see keys.normalize_query."""
    await cache.store("acme", "What is the retry limit?", answer())
    assert await cache.get_exact("acme", "  what is   the RETRY limit?  ") is not None


async def test_exact_cache_does_not_fold_punctuation(cache):
    """ERR_TIMEOUT_502 and ERR TIMEOUT 502 might mean different things, and
    v2.3 must not collapse into v23. The cache should be conservative about
    calling two questions identical."""
    await cache.store("acme", "what about ERR_TIMEOUT_502?", answer())
    assert await cache.get_exact("acme", "what about ERR TIMEOUT 502?") is None


async def test_miss_returns_none(cache):
    assert await cache.get_exact("acme", "never asked") is None


# ------------------------------------------------------ tenant isolation --


async def test_one_tenants_cache_is_invisible_to_another(cache):
    """Design.md §9: 'per-tenant cache namespace — cache bhi tenant-isolated
    honi chahiye (same leakage risk applies!)'. Phase 2 made cross-tenant
    reads impossible in SQL; serving one from Redis would walk around all of
    it."""
    await cache.store("acme", "shared question", answer(text="ACME ONLY SECRET"))

    assert await cache.get_exact("globex", "shared question") is None
    assert await cache.get_exact("acme", "shared question") is not None


async def test_semantic_cache_is_also_tenant_isolated(cache):
    """The fuzzy path needs its own test — it reads a different key space, so
    isolation on the exact path proves nothing about it."""
    query_vector = vector(1.0, 0.0)
    await cache.store("acme", "how do webhooks retry", answer(text="ACME ONLY"), query_vector)

    assert await cache.get_semantic("globex", "how do webhooks retry", query_vector) is None
    assert await cache.get_semantic("acme", "how do webhooks retry", query_vector) is not None


async def test_flushing_one_tenant_leaves_the_other_alone(cache):
    await cache.store("acme", "q", answer())
    await cache.store("globex", "q", answer())

    await cache.invalidate_tenant("acme")

    assert await cache.get_exact("acme", "q") is None
    assert await cache.get_exact("globex", "q") is not None


def test_a_key_cannot_be_built_without_a_tenant():
    """Same discipline as TenantScope: no way to construct a global key."""
    for bad in ("", None, 123):
        with pytest.raises(ValueError, match="tenant"):
            cache_keys.exact_key(bad, "q")


# ------------------------------------------------------ semantic cache --


async def test_semantic_hit_on_a_near_identical_vector(cache):
    stored = vector(1.0, 0.0)
    await cache.store("acme", "how do webhook retries work", answer(), stored)

    # cos ~= 0.9987, above the 0.95 threshold
    hit = await cache.get_semantic("acme", "how do webhook retries function", vector(1.0, 0.05))
    assert hit is not None
    assert hit.similarity is not None and hit.similarity > 0.95


async def test_semantic_miss_below_threshold(cache):
    await cache.store("acme", "how do webhook retries work", answer(), vector(1.0, 0.0))
    # cos ~= 0.707 — clearly a different question
    assert await cache.get_semantic("acme", "billing question", vector(1.0, 1.0)) is None


async def test_the_closest_entry_wins(cache):
    await cache.store("acme", "first", answer(text="FIRST"), vector(1.0, 0.30))
    await cache.store("acme", "second", answer(text="SECOND"), vector(1.0, 0.02))

    hit = await cache.get_semantic("acme", "probe", vector(1.0, 0.0))
    assert hit is not None and hit.answer == "SECOND"


# ------------------------------------------------- the identifier guard --


@pytest.mark.parametrize(
    "query",
    [
        "what causes ERR_TIMEOUT_502?",
        "what changed in v2.4?",
        "why am I getting a 429?",
        "what happened with ticket ACM-1041?",
        "is /v2/export still supported?",
    ],
)
def test_identifier_queries_are_detected(query):
    assert cache_keys.contains_identifier(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "how do webhooks retry",
        "why is my data not showing up",
        "how do I rotate an API key",
    ],
)
def test_ordinary_queries_are_not_flagged(query):
    assert cache_keys.contains_identifier(query) is False


async def test_two_error_codes_never_share_a_semantic_cache_entry(cache):
    """THE test this guard exists for.

    'What causes ERR_TIMEOUT_502?' and 'What causes ERR_TIMEOUT_504?' embed
    almost identically — both mean 'an error code for a failure in this
    product' — and have completely different answers. Vector similarity cannot
    tell them apart, and the semantic cache is pure vector similarity with no
    BM25 leg and no reranker to correct it.

    So identifier-bearing queries skip the fuzzy path entirely. The vectors
    below are deliberately near-identical to prove the guard fires on the
    QUERY TEXT, not on the score.
    """
    v502 = vector(1.0, 0.001)
    await cache.store("acme", "what causes ERR_TIMEOUT_502?", answer(text="502 ANSWER"), v502)

    hit = await cache.get_semantic("acme", "what causes ERR_TIMEOUT_504?", vector(1.0, 0.002))
    assert hit is None, "an error-code query must never be served from the semantic cache"


async def test_identifier_queries_still_use_the_exact_cache(cache):
    """The guard disables the FUZZY path only. An identical repeat question is
    still safely cacheable, and that is where most of the hit rate lives."""
    await cache.store("acme", "what causes ERR_TIMEOUT_502?", answer(text="502 ANSWER"))
    hit = await cache.get_exact("acme", "what causes ERR_TIMEOUT_502?")
    assert hit is not None and hit.answer == "502 ANSWER"


async def test_identifier_queries_are_not_stored_semantically(cache):
    """Guarded on write as well as read. Storing one would leave a landmine
    for a later query if the read-side guard were ever weakened."""
    await cache.store("acme", "errors for ERR_TIMEOUT_502", answer(), vector(1.0, 0.0))
    index = await cache.redis.zrange(cache_keys.semantic_index_key("acme"), 0, -1)
    assert index == []


# ------------------------------------------------------- invalidation --


async def test_reingesting_a_chunk_evicts_answers_built_on_it(cache):
    """Design.md §9's 'active invalidation'. Without it, a corrected document
    keeps serving the old answer until TTL — the exact stale-data failure the
    whole system is built to prevent."""
    await cache.store("acme", "q1", answer(chunk_ids=["chunk-a"]), vector(1.0, 0.0))
    await cache.store("acme", "q2", answer(chunk_ids=["chunk-b"]))

    removed = await cache.invalidate_chunks("acme", ["chunk-a"])

    assert removed >= 1
    assert await cache.get_exact("acme", "q1") is None
    assert await cache.get_exact("acme", "q2") is not None, "unrelated answers must survive"


async def test_invalidation_removes_the_semantic_entry_too(cache):
    """Both paths, or a stale answer survives on the fuzzy one — the harder
    failure to notice, because it only surfaces for a differently-worded
    question."""
    query_vector = vector(1.0, 0.0)
    await cache.store("acme", "how do webhooks retry", answer(chunk_ids=["chunk-a"]), query_vector)

    await cache.invalidate_chunks("acme", ["chunk-a"])

    assert await cache.get_exact("acme", "how do webhooks retry") is None
    assert await cache.get_semantic("acme", "how do webhooks retry", query_vector) is None


async def test_an_answer_using_several_chunks_dies_if_any_one_changes(cache):
    """Conservative on purpose. If any source it was built on changed, the
    answer may be wrong — regenerating costs one LLM call, serving a stale
    answer costs trust."""
    await cache.store("acme", "q", answer(chunk_ids=["a", "b", "c"]))
    await cache.invalidate_chunks("acme", ["b"])
    assert await cache.get_exact("acme", "q") is None


async def test_invalidating_unknown_chunks_is_harmless(cache):
    await cache.store("acme", "q", answer(chunk_ids=["a"]))
    assert await cache.invalidate_chunks("acme", ["never-seen"]) == 0
    assert await cache.get_exact("acme", "q") is not None


async def test_invalidation_is_tenant_scoped(cache):
    """Two tenants can hold the same chunk id in their reverse indexes only
    within their own namespace. Re-ingesting acme must not empty globex."""
    await cache.store("acme", "q", answer(chunk_ids=["shared"]))
    await cache.store("globex", "q", answer(chunk_ids=["shared"]))

    await cache.invalidate_chunks("acme", ["shared"])

    assert await cache.get_exact("acme", "q") is None
    assert await cache.get_exact("globex", "q") is not None


# ----------------------------------------------------------- robustness --


async def test_empty_answers_are_not_cached(cache):
    await cache.store("acme", "q", answer(text="   "))
    assert await cache.get_exact("acme", "q") is None


async def test_a_disabled_cache_is_a_no_op(cache, redis):
    disabled = AnswerCache(redis, enabled=False)
    await disabled.store("acme", "q", answer())
    assert await disabled.get_exact("acme", "q") is None


async def test_a_broken_redis_degrades_instead_of_raising():
    """A cache is an optimization. If Redis is down the system must get
    slower, never break — so every call is wrapped and a failure reads as a
    miss."""
    class BrokenRedis:
        def __getattr__(self, name):
            def explode(*args, **kwargs):
                raise ConnectionError("redis is down")
            return explode

    broken = AnswerCache(BrokenRedis())
    assert await broken.get_exact("acme", "q") is None
    assert await broken.get_semantic("acme", "q", [1.0, 0.0]) is None
    await broken.store("acme", "q", answer())          # must not raise
    assert await broken.invalidate_chunks("acme", ["a"]) == 0


async def test_corrupt_entry_reads_as_a_miss(cache):
    await cache.redis.set(cache_keys.exact_key("acme", "q"), "{not json")
    assert await cache.get_exact("acme", "q") is None


def test_cosine_similarity_edges():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0


async def test_cached_answer_reports_its_age(cache):
    stored = answer()
    stored.cached_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)
    await cache.store("acme", "q", stored)
    hit = await cache.get_exact("acme", "q")
    assert hit is not None and hit.age_seconds() >= 119
