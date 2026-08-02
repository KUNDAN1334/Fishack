"""Request tracing (Design.md §12).

One row per request in the `traces` table — the observability backbone the
Phase 5 `/stats` endpoint aggregates over and the Phase 5 feedback triage
joins against. The table has existed since Phase 0; Phase 3 is where it starts
being written.
"""
