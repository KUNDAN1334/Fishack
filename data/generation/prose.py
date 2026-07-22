"""LLM prose filler with an on-disk cache and an offline fallback.

The hybrid corpus (ADR-008) uses the LLM for BODY TEXT ONLY — never for
facts that the evals depend on. Every number, error code, version and date
comes from spec.py and is passed into the prompt as a constraint.

Three properties that matter:

1. CACHED. Every generation is keyed by sha256(prompt) and written to
   data/generation/.prose_cache/. Re-running the generator costs zero
   quota and produces identical output. The cache is committed so a fresh
   clone reproduces the corpus byte-for-byte without any API key.

2. OFFLINE FALLBACK. With no key and no cache entry, `TemplateProse`
   produces deterministic, structurally-valid filler. The repo always
   works; prose is just blander.

3. FACT-PRESERVING. The prompt instructs the model to include the hint's
   specifics verbatim. A post-check warns when a required literal
   (e.g. "5 attempts") is missing from the generated text.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path

from app.llm.base import ChatMessage
from app.llm.client import AllProvidersFailedError, LLMClient

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / ".prose_cache"

SYSTEM_PROMPT = """You write technical documentation for Flowlytics, a B2B \
SaaS analytics and billing platform.

Rules:
- Write ONLY the body prose. No headings, no title, no preamble, no closing.
- Plain markdown paragraphs. Short lists are fine. No code fences unless the \
brief asks for an example.
- Every specific figure, limit, error code or version in the brief MUST appear \
verbatim in your text. Do not round, rename, or paraphrase them.
- Do not invent figures the brief does not give you.
- Professional, concise, factual. No marketing language.
- 90-150 words unless the brief says otherwise."""


def cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:24]


class ProseGenerator:
    """Async prose generator with disk cache. `client=None` => offline mode."""

    def __init__(self, client: LLMClient | None, cache_dir: Path = CACHE_DIR):
        self.client = client
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"cache_hits": 0, "generated": 0, "fallback": 0, "fact_warnings": 0}

    # ------------------------------------------------------------- prompts --

    @staticmethod
    def build_prompt(context: str, hint: str, words: str = "90-150 words") -> str:
        return (
            f"Document context: {context}\n"
            f"Section brief: {hint}\n"
            f"Length: {words}\n\n"
            f"Write the section body now."
        )

    # --------------------------------------------------------------- cache --

    def _cache_path(self, prompt: str) -> Path:
        return self.cache_dir / f"{cache_key(prompt)}.md"

    def read_cache(self, prompt: str) -> str | None:
        path = self._cache_path(prompt)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_cache(self, prompt: str, text: str) -> None:
        self._cache_path(prompt).write_text(text, encoding="utf-8")

    # ---------------------------------------------------------- generation --

    async def generate(self, context: str, hint: str, words: str = "90-150 words") -> str:
        """Return prose for one section: cache -> LLM -> template fallback."""
        prompt = self.build_prompt(context, hint, words)

        cached = self.read_cache(prompt)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached

        if self.client is not None:
            try:
                response = await self.client.complete(
                    [
                        ChatMessage(role="system", content=SYSTEM_PROMPT),
                        ChatMessage(role="user", content=prompt),
                    ],
                    temperature=0.4,  # higher than the app's 0.1: we WANT prose variety here
                    max_tokens=400,
                )
                text = _clean(response.text)
                if text:
                    self._check_facts(hint, text)
                    self.write_cache(prompt, text)
                    self.stats["generated"] += 1
                    return text
                logger.warning("empty generation, falling back to template")
            except AllProvidersFailedError as exc:
                # Quota exhausted mid-run is EXPECTED on free tiers. Fall back
                # rather than aborting: the corpus still generates, and a
                # later re-run fills the gaps from cache + fresh quota.
                logger.warning("all providers failed, using template fallback: %s", exc)

        self.stats["fallback"] += 1
        return template_prose(context, hint)

    def _check_facts(self, hint: str, text: str) -> None:
        """Warn if a literal the evals depend on didn't survive generation.

        Checks numbers-with-units and ERR_* codes appearing in the hint.
        A warning, not an error: the generator shouldn't hard-fail a 100-doc
        run, but you want to know before building a golden set on it.
        """
        required = set(re.findall(r"ERR_[A-Z0-9_]+", hint))
        required |= set(re.findall(r"\$?\d[\d,]*(?:\.\d+)?", hint))
        missing = [token for token in required if token not in text]
        if missing:
            self.stats["fact_warnings"] += 1
            logger.warning("generated prose dropped required literals %s for hint: %.60s",
                           missing, hint)


def _clean(text: str) -> str:
    """Strip the boilerplate LLMs add despite instructions."""
    text = text.strip()
    text = re.sub(r"^(Here'?s?|Here is)[^\n]*\n+", "", text, flags=re.IGNORECASE)
    # Drop any heading lines the model added anyway — the doc structure comes
    # from spec.py, and a stray "## " would corrupt the structure-aware chunker
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith("#")]
    return "\n".join(lines).strip()


# ------------------------------------------------------------- fallback -----

def template_prose(context: str, hint: str) -> str:
    """Deterministic filler used when no LLM and no cache are available.

    Deliberately preserves the hint text so the facts the evals need are
    still present in the corpus — a bland corpus that is FACTUALLY correct
    is far more useful than pretty prose that lost the numbers.
    """
    subject = hint.split(",")[0].strip().rstrip(".")
    return (
        f"{subject.capitalize()}. This section of {context} describes the behaviour in detail "
        f"for Flowlytics customers.\n\n"
        f"{hint.capitalize()}. Customers should review the configuration in the workspace "
        f"settings page before relying on this behaviour in production.\n\n"
        f"If the behaviour described here does not match what you observe, check the pipeline "
        f"health page first, then contact support with your workspace identifier and a recent "
        f"request_id."
    )


async def generate_many(
    generator: ProseGenerator,
    jobs: list[tuple[str, str, str]],
    concurrency: int = 3,
) -> list[str]:
    """Run prose jobs with a concurrency cap.

    concurrency=3: free tiers rate-limit aggressively (OpenRouter ~20 req/min).
    The client retries and fails over, but staying under the limit is cheaper
    than recovering from it. Same lesson the eval harness applies in Phase 4.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def run(job: tuple[str, str, str]) -> str:
        async with semaphore:
            return await generator.generate(*job)

    return await asyncio.gather(*(run(job) for job in jobs))
