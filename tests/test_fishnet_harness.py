"""The rest of the harness: golden-set I/O, judge parsing, assertions, the
baseline gate, and the naive chunker's windowing.

All pure — no database, no LLM. The harness has to be trustworthy before its
numbers mean anything, so its own logic is tested the same way the app's is.
"""

import datetime as dt
import json

import pytest

from app.generation.models import ChatResponse, Citation, CitationReport
from app.ingestion.chunkers.naive import _split_fixed
from fishnet.assertions import run_assertions
from fishnet.baseline import compare, write_baseline
from fishnet.judge import _clamp, parse_judge_response
from fishnet.models import GoldenCase, SourceLocator, load_cases, save_cases


def case(**kwargs) -> GoldenCase:
    defaults = dict(case_id="c1", case_type="normal", tenant_id="acme", query="q")
    defaults.update(kwargs)
    return GoldenCase(**defaults)


def response(**kwargs) -> ChatResponse:
    defaults = dict(answer="Retries cap at five attempts [1].", action="answered")
    defaults.update(kwargs)
    return ChatResponse(**defaults)


# ------------------------------------------------------------ golden set --


def test_golden_set_round_trips(tmp_path):
    path = tmp_path / "golden.jsonl"
    cases = [
        case(case_id="a", expected_sources=[SourceLocator(source_type="docs", slug="x")]),
        case(case_id="b", case_type="out_of_scope"),
    ]
    save_cases(path, cases)
    assert [c.case_id for c in load_cases(path)] == ["a", "b"]


def test_saving_is_byte_stable(tmp_path):
    """Re-saving an unchanged set must produce an identical file, or every
    regeneration shows a spurious diff and people stop reading them."""
    path = tmp_path / "golden.jsonl"
    cases = [case(case_id="a"), case(case_id="b")]
    save_cases(path, cases)
    first = path.read_bytes()
    save_cases(path, load_cases(path))
    assert path.read_bytes() == first


def test_duplicate_case_ids_are_rejected(tmp_path):
    """Duplicates would double-count in aggregates and make two different
    cases indistinguishable in a report."""
    path = tmp_path / "golden.jsonl"
    path.write_text(
        json.dumps(case(case_id="dup").model_dump(mode="json")) + "\n"
        + json.dumps(case(case_id="dup").model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate case_id"):
        load_cases(path)


def test_load_reports_the_line_number_on_bad_json(tmp_path):
    """With 60 cases in a file, 'invalid JSON' without a position is a
    scavenger hunt."""
    path = tmp_path / "golden.jsonl"
    path.write_text(
        json.dumps(case(case_id="ok").model_dump(mode="json")) + "\n{not json\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=":2:"):
        load_cases(path)


def test_must_abstain_is_derived_from_case_type():
    assert case(case_type="out_of_scope").must_abstain is True
    assert case(case_type="normal").must_abstain is False


def test_locator_describe_is_readable():
    assert SourceLocator(source_type="docs", slug="webhooks", heading="Retry").describe() == (
        "docs:webhooks > Retry"
    )
    assert SourceLocator(source_type="ticket", ticket_id="ACM-1041").describe() == (
        "ticket:ACM-1041"
    )


# ---------------------------------------------------------------- judge --


@pytest.mark.parametrize(
    "raw",
    [
        '{"faithfulness": 0.8, "citation_accuracy": 1.0, "answer_relevance": 0.9}',
        '```json\n{"faithfulness": 0.8, "citation_accuracy": 1.0, "answer_relevance": 0.9}\n```',
        'Here is my verdict:\n{"faithfulness": 0.8, "citation_accuracy": 1.0, '
        '"answer_relevance": 0.9}\nHope that helps.',
    ],
)
def test_judge_output_is_extracted_from_prose_and_fences(raw):
    """Models wrap JSON despite being told not to. Handling it in code is
    cheaper and more reliable than another prompt iteration."""
    parsed = parse_judge_response(raw)
    assert parsed["faithfulness"] == 0.8


def test_unparseable_judge_output_returns_none():
    """None becomes `skipped`, never a score of 0.0 — a flaky judge must not
    look like a quality regression."""
    assert parse_judge_response("I think the answer was pretty good.") is None
    assert parse_judge_response("") is None
    assert parse_judge_response("{broken json") is None


@pytest.mark.parametrize(
    "value,expected",
    [(0.75, 0.75), (1.0, 1.0), (0.0, 0.0), (8, 0.8), (95, 0.95), (-1, 0.0), ("0.5", 0.5)],
)
def test_judge_scores_are_coerced_into_zero_one(value, expected):
    """Judges answer on a 0-10 or 0-100 scale despite the rubric. Coerce
    rather than discard — a rescaled score is still information."""
    assert _clamp(value) == pytest.approx(expected)


def test_unparseable_score_becomes_none_not_zero():
    assert _clamp("very good") is None
    assert _clamp(None) is None


# ----------------------------------------------------------- assertions --


def test_must_abstain_fails_when_an_out_of_scope_question_is_answered():
    """The single most important check in the harness — it measures the
    behaviour the gate, the closed-book prompt AND the few-shot examples were
    all built to produce."""
    results = run_assertions(
        case(case_type="out_of_scope"),
        response(answer="The capital of France is Paris.", action="answered"),
    )
    check = next(r for r in results if r.name == "must_abstain")
    assert check.passed is False
    assert "ANSWERED" in check.detail


def test_must_abstain_passes_on_an_abstention():
    results = run_assertions(
        case(case_type="out_of_scope"),
        response(answer="I don't have enough information.", action="escalated"),
    )
    assert next(r for r in results if r.name == "must_abstain").passed is True


def test_must_abstain_is_not_applied_to_normal_cases():
    """Checks that do not apply are dropped, so '3/3 passed' never includes
    checks that were skipped."""
    names = {r.name for r in run_assertions(case(case_type="normal"), response())}
    assert "must_abstain" not in names


def test_fabricated_citations_fail():
    results = run_assertions(
        case(),
        response(
            citations=[
                Citation(
                    index=1, chunk_id="c1", document_id="d1",
                    title="Doc", source_type="docs", source_path="d.md",
                )
            ],
            citation_report=CitationReport(invalid_indices=[9]),
        ),
    )
    check = next(r for r in results if r.name == "no_fabricated_citations")
    assert check.passed is False


def test_must_contain_catches_a_fluent_answer_that_omits_the_figure():
    """The failure the LLM judge is worst at: plausible prose that never names
    the number it was asked about."""
    results = run_assertions(
        case(must_contain=["5"]),
        response(answer="Webhook deliveries are retried several times with backoff [1]."),
    )
    check = next(r for r in results if r.name == "must_contain")
    assert check.passed is False
    assert "['5']" in check.detail


def test_must_contain_passes_when_the_literal_is_present():
    results = run_assertions(
        case(must_contain=["5"]),
        response(answer="Deliveries are retried up to 5 times [1]."),
    )
    assert next(r for r in results if r.name == "must_contain").passed is True


def test_cross_tenant_leak_detected_in_answer_text():
    """Catches a leak that reached the ANSWER by a route the chunk-level check
    cannot see — a mis-namespaced cache, a prompt-assembly bug."""
    results = run_assertions(
        case(case_type="cross_tenant", forbidden_text="globex"),
        response(answer="According to the Globex onboarding runbook, ..."),
    )
    check = next(r for r in results if r.name == "no_cross_tenant_leak")
    assert check.passed is False


def test_cross_tenant_passes_when_clean():
    results = run_assertions(
        case(case_type="cross_tenant", forbidden_text="globex"),
        response(answer="I don't have enough information.", action="escalated"),
    )
    assert next(r for r in results if r.name == "no_cross_tenant_leak").passed is True


# ------------------------------------------------------------- baseline --


def summary(recall=0.8, faithfulness=0.9, assertion_failures=0, judged=60) -> dict:
    return {
        "cases_total": 60,
        "retrieval": {"overall": {"recall@5": recall, "recall@20": 0.9, "mrr": 0.7}},
        "generation": {"faithfulness": faithfulness, "citation_accuracy": 0.9, "judged": judged},
        "assertions": {"must_abstain": {"passed": 10, "failed": assertion_failures}},
        "cost": {},
    }


def test_missing_baseline_passes():
    """The first run on a fresh clone must not block CI, or nobody can ever
    create a baseline."""
    verdict = compare(summary(), None)
    assert verdict.passed is True and verdict.missing_baseline is True


def test_small_drop_within_tolerance_passes():
    verdict = compare(summary(recall=0.78), summary(recall=0.80), tolerance=0.05)
    assert verdict.passed is True


def test_large_drop_fails():
    verdict = compare(summary(recall=0.60), summary(recall=0.80), tolerance=0.05)
    assert verdict.passed is False
    assert any(c.regressed for c in verdict.comparisons)


def test_improvement_never_fails():
    """Sounds obvious until you write `abs(delta) > tolerance` and start
    failing builds for getting better."""
    verdict = compare(summary(recall=0.95), summary(recall=0.80), tolerance=0.05)
    assert verdict.passed is True


def test_any_assertion_failure_fails_regardless_of_baseline():
    """Zero tolerance. There is no acceptable rate of cross-tenant leakage,
    and a percentage band on a correctness check is how a security bug gets
    absorbed by a quality budget."""
    verdict = compare(summary(assertion_failures=1), summary(assertion_failures=0))
    assert verdict.passed is False
    assert verdict.assertion_failures


def test_generation_metrics_are_skipped_when_the_judge_barely_ran():
    """Comparing a score over 8 cases against a baseline over 60 is not a
    comparison. On a free tier, quota-limited runs are common enough that
    failing on them would train people to ignore the gate."""
    verdict = compare(summary(faithfulness=0.1, judged=5), summary(faithfulness=0.9))
    names = {c.name for c in verdict.comparisons}
    assert "generation.faithfulness" not in names
    assert verdict.passed is True


def test_write_baseline_excludes_per_case_detail(tmp_path):
    path = tmp_path / "baseline.json"
    write_baseline(path, summary() | {"run_id": "x", "cases": ["should not appear"]})
    written = json.loads(path.read_text())
    assert "cases" not in written
    assert "retrieval" in written


# --------------------------------------------------------- naive chunker --


def test_naive_windows_cover_the_whole_text():
    text = "word " * 2000
    windows = _split_fixed(text, 1600, 240)
    assert len(windows) > 1
    assert windows[0].startswith("word")


def test_naive_windows_overlap():
    """Overlap must actually happen, or the baseline is unfairly weak — an
    experiment that only wins against an incompetent control proves little."""
    text = ". ".join(f"sentence number {i}" for i in range(400))
    windows = _split_fixed(text, 1600, 240)
    assert len(windows) >= 2
    tail = windows[0][-100:]
    assert any(fragment in windows[1] for fragment in tail.split(". ") if len(fragment) > 8)


def test_naive_split_rejects_overlap_larger_than_size():
    """Would make the loop unable to advance — an infinite loop rather than a
    wrong answer."""
    with pytest.raises(ValueError, match="smaller than size"):
        _split_fixed("text", 100, 100)


def test_naive_split_on_short_text_returns_one_window():
    assert _split_fixed("short", 1600, 240) == ["short"]


def test_naive_split_terminates_on_pathological_input():
    """No paragraph or sentence boundaries anywhere — the boundary search
    finds nothing and the window must still advance."""
    windows = _split_fixed("x" * 10_000, 1600, 240)
    assert len(windows) > 1
    assert sum(len(w) for w in windows) >= 10_000


# ------------------------------------------- the ordering the eval scores --


def _scored(chunk_id: str, rerank: float | None = None):
    from app.retrieval.models import RetrievedChunk, ScoredChunk

    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=chunk_id, document_id=f"d-{chunk_id}", tenant_id="acme", content="x"
        ),
        fused_score=0.02,
        rerank_score=rerank,
    )


def test_eval_scores_the_reranked_order_not_the_fusion_order():
    """The bug that made a working reranker look like a no-op.

    `RetrievalService` sets `candidates` BEFORE reranking, and reranking
    returns a new sorted list into `results` rather than resorting
    `candidates`. Scoring `candidates` therefore measured the pre-rerank
    ranking — so the `hybrid` and `hybrid+rerank` arms produced byte-identical
    scorecards while the cross-encoder burned 1.4s per case doing work the
    eval discarded. It would have led straight to "reranking is not worth the
    latency", which is the opposite of what the data showed.
    """
    from app.retrieval.models import RetrievalResult
    from fishnet.run import EvalRunner

    retrieval = RetrievalResult(
        query="q", tenant_id="acme", mode="hybrid",
        # Fusion put "wrong" first; the reranker promoted "right".
        candidates=[_scored("wrong"), _scored("right"), _scored("third")],
        results=[_scored("right", rerank=0.9), _scored("wrong", rerank=0.2)],
    )

    order = EvalRunner._effective_order(retrieval)
    assert order[0] == "right", "metrics must see the reranked order"
    assert order == ["right", "wrong", "third"]


def test_effective_order_keeps_unreranked_candidates_for_recall_at_20():
    """Only `rerank_input_top_k` candidates reach the cross-encoder. The rest
    must still be counted, or recall@20 would silently become recall@8."""
    from app.retrieval.models import RetrievalResult
    from fishnet.run import EvalRunner

    retrieval = RetrievalResult(
        query="q", tenant_id="acme", mode="hybrid",
        candidates=[_scored(f"c{i}") for i in range(20)],
        results=[_scored("c7", rerank=0.9), _scored("c0", rerank=0.5)],
    )

    order = EvalRunner._effective_order(retrieval)
    assert order[:2] == ["c7", "c0"]
    assert len(order) == 20
    assert len(set(order)) == 20, "no chunk may be counted twice"


def test_effective_order_without_a_reranker_is_the_fusion_order():
    from app.retrieval.models import RetrievalResult
    from fishnet.run import EvalRunner

    candidates = [_scored(f"c{i}") for i in range(5)]
    retrieval = RetrievalResult(
        query="q", tenant_id="acme", mode="hybrid",
        candidates=candidates, results=candidates[:5],
    )
    assert EvalRunner._effective_order(retrieval) == [f"c{i}" for i in range(5)]
