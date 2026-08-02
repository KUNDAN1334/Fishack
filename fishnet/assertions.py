"""Hard assertions — correctness, not quality (Design.md §12).

    "plus hard assertions: abstention cases MUST abstain, out-of-context cases
     MUST NOT answer."

The distinction from every other number in this harness is worth being precise
about. Recall, MRR and faithfulness are QUALITY metrics: they move
continuously, they are noisy, they trade against each other, and a small drop
is a signal to investigate rather than a reason to stop. These are CORRECTNESS
checks. There is no acceptable rate of cross-tenant leakage. There is no
tolerance band on "answered a question it had no information for". They pass
or the build fails (ADR-022).

Which is why they live in their own module and are aggregated separately in
the scorecard. Folding a must-abstain failure into an average faithfulness
score would let a 5% quality tolerance absorb a security bug.
"""

from __future__ import annotations

from app.generation.models import ChatResponse
from fishnet.models import AssertionResult, GoldenCase


def check_must_abstain(case: GoldenCase, response: ChatResponse) -> AssertionResult | None:
    """Out-of-scope questions must be refused, not answered.

    This is the assertion protecting against the failure Design.md exists to
    prevent: a confident, fluent, well-cited answer to a question the corpus
    does not address. It is the single most important check in the harness,
    because it is the only one measuring the behaviour the confidence gate,
    the closed-book prompt and the few-shot abstention examples were ALL built
    to produce.
    """
    if not case.must_abstain:
        return None
    passed = response.is_abstention
    return AssertionResult(
        name="must_abstain",
        passed=passed,
        detail=(
            "abstained as required" if passed
            else f"ANSWERED an out-of-scope question: {response.answer[:180]!r}"
        ),
    )


def check_no_cross_tenant_leak(case: GoldenCase, response: ChatResponse) -> AssertionResult | None:
    """No chunk from another tenant, ever.

    Two independent checks, because they fail differently. The chunk-level one
    catches a retrieval leak (a foreign `chunk_id` in the citations). The text
    one catches a leak that got through anyway and reached the answer — for
    instance via a cached response or a prompt-assembly bug — which the
    chunk-level check cannot see.
    """
    if case.case_type != "cross_tenant":
        return None

    problems: list[str] = []

    # Chunk level. `Citation` carries no tenant_id (it is a presentation type),
    # so this reads the retrieval result, where every RetrievedChunk does.
    # In practice TenantScope's tripwire raises before we ever get here — this
    # is defense in depth, and it is the assertion that would catch a leak
    # introduced by some future path that bypasses the scope.
    if response.retrieval is not None:
        foreign = [
            scored.chunk.chunk_id
            for scored in response.retrieval.candidates
            if scored.chunk.tenant_id != case.tenant_id
        ]
        if foreign:
            problems.append(f"retrieved chunks from another tenant: {foreign}")

    # Text level. Catches a leak that reached the ANSWER by some route the
    # chunk check cannot see — a cache with the wrong namespace (Phase 5), a
    # prompt-assembly bug, history carried across tenants.
    if case.forbidden_text and case.forbidden_text.lower() in response.answer.lower():
        problems.append(f"answer contains tenant-exclusive text {case.forbidden_text!r}")

    return AssertionResult(
        name="no_cross_tenant_leak",
        passed=not problems,
        detail="; ".join(problems) if problems else "no foreign content",
    )


def check_no_fabricated_citations(case: GoldenCase, response: ChatResponse) -> AssertionResult | None:
    """A citation marker pointing at a source that was never offered.

    Unambiguous — it needs no model and no threshold to detect, which is
    exactly what makes it assertable rather than merely measurable. Skipped
    for abstentions, which cite nothing by design.
    """
    if response.is_abstention or response.citation_report is None:
        return None
    invalid = response.citation_report.invalid_indices
    return AssertionResult(
        name="no_fabricated_citations",
        passed=not invalid,
        detail=(
            "all citation markers valid" if not invalid
            else f"cited non-existent sources {invalid} (only 1..{len(response.citations)} offered)"
        ),
    )


def check_must_contain(case: GoldenCase, response: ChatResponse) -> AssertionResult | None:
    """Required literals — an error code, a version, a number.

    A cheap deterministic complement to the LLM judge: it costs nothing, never
    drifts between runs, and catches the specific failure the judge is worst
    at, which is a fluent answer that quietly omits the actual figure. For a
    stale-data case, `must_contain=["5"]` is the whole point — the answer has
    to carry the NEW value, not just discuss retries plausibly.
    """
    if not case.must_contain or response.is_abstention:
        return None
    answer = response.answer.lower()
    missing = [literal for literal in case.must_contain if literal.lower() not in answer]
    return AssertionResult(
        name="must_contain",
        passed=not missing,
        detail="all required literals present" if not missing else f"missing {missing}",
    )


def run_assertions(case: GoldenCase, response: ChatResponse) -> list[AssertionResult]:
    """Every assertion applicable to this case.

    Checks that do not apply return None and are dropped, so a case's
    assertion list contains only things that were actually verified — a report
    showing "3/3 passed" must not include checks that were skipped.
    """
    checks = [
        check_must_abstain(case, response),
        check_no_cross_tenant_leak(case, response),
        check_no_fabricated_citations(case, response),
        check_must_contain(case, response),
    ]
    return [check for check in checks if check is not None]
