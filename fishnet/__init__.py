"""fishnet — Fishly's eval harness (it catches bad answers).

A first-class module, not a test folder: `python -m fishnet.run` in
development, `make eval` in CI.

    models.py       GoldenCase, case types, run reports
    resolver.py     stable locators -> chunk_ids, resolved per run
    metrics.py      recall@k, precision@k, MRR — pure functions
    judge.py        LLM-as-judge: faithfulness + citation accuracy
    assertions.py   hard pass/fail checks (must-abstain, must-not-leak)
    scorecard.py    the printed table and the JSON report
    baseline.py     regression detection against a committed baseline
    run.py          the CLI

The organizing principle, from Design.md §12: retrieval quality and
generation quality are measured SEPARATELY, because they are independent
failure points. If retrieval is broken, generation metrics are meaningless —
garbage in, garbage out — and averaging them into one "quality score" hides
exactly the thing you needed to know.
"""
