"""HTTP surface.

Routers are thin: they validate input, resolve the tenant, and hand off to a
pipeline. No retrieval or generation logic lives here — the eval harness
(Phase 4) drives the same pipelines without going through HTTP, and anything
that leaked into a route handler would be untested by it.
"""
