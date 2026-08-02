"""Golden-set and report types.

The central design decision here is how ground truth is IDENTIFIED (ADR-019).

The obvious answer — store the chunk UUIDs a query should retrieve — is
wrong, and wrong in a way that would not show up for weeks. Chunk ids are
generated at ingest time, so:

  * re-ingesting the corpus invalidates the entire golden set silently: every
    case now points at rows that no longer exist, recall drops to zero, and it
    looks like a catastrophic retrieval regression;
  * the Phase 4 chunking experiment becomes impossible, because the naive-
    chunking arm produces completely different chunks. You cannot compare two
    chunking strategies using ground truth expressed in the chunk ids of one
    of them.

So a case stores a STABLE LOCATOR — "the Retry Logic section of the
webhooks-overview page", "ticket ACM-1041", "changelog entry CL-2026-0610-01"
— and `resolver.py` turns those into chunk ids at the start of each run,
against whatever corpus is currently loaded. Ground truth then survives
re-ingestion, re-chunking, and A/B chunking comparisons, because it is
expressed in terms of the SOURCE rather than the artifact.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# The six case types from the assignment. Metrics are reported per type,
# because an aggregate hides the interesting failures: a system can score 0.85
# recall overall while getting every exact-identifier case wrong, and
# identifier queries are precisely why the BM25 leg exists.
CaseType = Literal[
    "normal",              # a straightforward question answerable from one source
    "multi_turn",          # a follow-up needing conversation history to resolve
    "exact_identifier",    # ERR_TIMEOUT_502, v2.4 — where vector search fumbles
    "stale_conflict",      # doc and changelog disagree; must prefer newest AND flag it
    "out_of_scope",        # MUST abstain — nothing in the corpus answers it
    "cross_tenant",        # MUST NOT return the other tenant's chunks
]

# Types where a correct system refuses to answer. Kept as a set rather than
# scattered `if case_type == ...` checks so "which cases must abstain?" has
# exactly one answer in the codebase.
#
# `cross_tenant` belongs here and was missing in the first version, which
# produced eight spurious "case cannot score above 0" warnings on the very
# first real run. The semantics are the same as out_of_scope: asking tenant A
# about tenant B's private document is a question A's corpus genuinely cannot
# answer, so abstaining is the correct behaviour and expecting zero chunks is
# the assertion, not a defect.
#
# Including it also STRENGTHENS the check. A cross-tenant case now asserts two
# things: no foreign chunk leaked, AND the system did not paper over the gap
# with its own similar-looking document. Acme has its own onboarding runbook —
# answering "what does the Globex Onboarding Runbook say?" from it would leak
# nothing and still be a lie.
MUST_ABSTAIN_TYPES: frozenset[str] = frozenset({"out_of_scope", "cross_tenant"})


class SourceLocator(BaseModel):
    """Points at a source, not at a chunk. See the module docstring.

    Exactly one identifying field is set per source type:
      docs      -> slug (+ optional heading, to narrow to one section)
      changelog -> entry_id
      ticket    -> ticket_id
    """

    source_type: Literal["docs", "changelog", "ticket"]
    slug: str | None = None       # doc slug, e.g. "webhooks-overview"
    heading: str | None = None    # substring of heading_path, e.g. "Retry Logic"
    entry_id: str | None = None   # e.g. "CL-2026-0610-01"
    ticket_id: str | None = None  # e.g. "ACM-1041"

    def describe(self) -> str:
        """Human-readable, for scorecards and failure output."""
        if self.source_type == "docs":
            return f"docs:{self.slug}" + (f" > {self.heading}" if self.heading else "")
        return f"{self.source_type}:{self.entry_id or self.ticket_id}"


class GoldenCase(BaseModel):
    """One evaluation case.

    Stored as JSONL in `data/golden/` and committed, so a change to ground
    truth is a reviewable diff rather than an invisible drift. `case_id` is
    stable and human-assigned; reordering the file must not renumber cases, or
    every report becomes incomparable with the last one.
    """

    case_id: str
    case_type: CaseType
    tenant_id: str
    query: str

    # Prior turns for multi_turn cases. Empty otherwise.
    history: list[dict[str, str]] = Field(default_factory=list)

    # The sources that SHOULD be retrieved. Resolved to chunk ids at run time.
    # Empty for out_of_scope cases — there is nothing correct to retrieve, and
    # that emptiness is itself the assertion.
    expected_sources: list[SourceLocator] = Field(default_factory=list)

    # What a good answer says. Used by the LLM judge for reference-guided
    # scoring, and by a human reading a failure. Deliberately prose, not a
    # string to match: exact-match scoring on generated text measures
    # phrasing, not correctness.
    reference_answer: str = ""

    # Literals that must appear in a correct answer — an error code, a
    # version, a number. A cheap deterministic check alongside the judge, and
    # the only one that costs nothing and cannot drift between runs.
    must_contain: list[str] = Field(default_factory=list)

    # For cross_tenant cases: a string that exists ONLY in the other tenant's
    # corpus and must never appear in this tenant's results.
    forbidden_text: str | None = None

    notes: str = ""

    @property
    def must_abstain(self) -> bool:
        return self.case_type in MUST_ABSTAIN_TYPES


class RetrievalScores(BaseModel):
    """Per-case retrieval measurements (Design.md §12 offline evaluation)."""

    expected_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)  # ordered, best first
    recall_at_5: float = 0.0
    recall_at_20: float = 0.0
    precision_at_5: float = 0.0
    mrr: float = 0.0
    # Locators that resolved to nothing. A non-empty list means the golden set
    # and the corpus have diverged — reported loudly, because it would
    # otherwise look like a retrieval regression.
    unresolved: list[str] = Field(default_factory=list)


class JudgeScores(BaseModel):
    """LLM-as-judge output (Design.md §12: faithfulness, citation accuracy)."""

    faithfulness: float | None = None       # 0-1: is every claim supported by context?
    citation_accuracy: float | None = None  # 0-1: do the cited sources support their claims?
    answer_relevance: float | None = None   # 0-1: does it address the question asked?
    reasoning: str = ""
    judge_model: str = ""
    # True when the judge could not be run (quota, parse failure). Distinct
    # from a score of 0.0 — "not measured" and "measured as terrible" must
    # never be averaged together.
    skipped: bool = False
    skip_reason: str | None = None


class AssertionResult(BaseModel):
    """One hard pass/fail check. Correctness, not quality — no tolerance."""

    name: str
    passed: bool
    detail: str = ""


class CaseResult(BaseModel):
    """Everything one case produced. Serialized into the resume file, so a
    quota exhaustion mid-run loses nothing already computed."""

    case_id: str
    case_type: CaseType
    tenant_id: str
    arm: str = "hybrid+rerank"

    retrieval: RetrievalScores = Field(default_factory=RetrievalScores)
    judge: JudgeScores = Field(default_factory=JudgeScores)
    assertions: list[AssertionResult] = Field(default_factory=list)

    answer: str = ""
    action: str = ""
    confidence: float = 0.0
    abstained: bool = False
    must_contain_hits: int = 0
    must_contain_total: int = 0

    retrieval_ms: int = 0
    rerank_ms: int = 0
    generation_ms: int = 0
    total_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    virtual_cost_usd: float = 0.0

    error: str | None = None

    @property
    def assertions_passed(self) -> bool:
        return all(assertion.passed for assertion in self.assertions)


class RunReport(BaseModel):
    """One complete eval run — printed as a table, written as timestamped JSON.

    Records the CONFIGURATION as well as the numbers. A scorecard without the
    thresholds, model names and knob values that produced it cannot be
    compared against another one; you would be diffing two runs that differ
    in ways the report does not show.
    """

    run_id: str
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    git_sha: str | None = None

    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    generator_model: str = ""
    judge_model: str = ""

    cases_total: int = 0
    cases_run: int = 0
    results: list[CaseResult] = Field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


# ------------------------------------------------------------ JSONL I/O ----
# JSONL, not JSON: one case per line means a golden-set diff shows which CASES
# changed rather than reflowing the whole file, and a malformed line can be
# located and fixed without a parser hunt.


def load_cases(path: Path) -> list[GoldenCase]:
    """Read a golden set. Line numbers are reported on failure — with 60 cases
    in one file, "invalid JSON" without a line number is a scavenger hunt."""
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                case = GoldenCase.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001 — re-raised with position
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if case.case_id in seen:
                # Duplicate ids would double-count in aggregates and make two
                # different cases indistinguishable in a report.
                raise ValueError(f"{path}:{line_number}: duplicate case_id {case.case_id!r}")
            seen.add(case.case_id)
            cases.append(case)
    return cases


def save_cases(path: Path, cases: list[GoldenCase]) -> None:
    """Write a golden set with stable key ordering, so re-saving an unchanged
    set produces a byte-identical file and the diff is empty."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(
                json.dumps(case.model_dump(mode="json", exclude_defaults=False),
                           ensure_ascii=False, sort_keys=True)
                + "\n"
            )
