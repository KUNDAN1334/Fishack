"""Synthetic corpus generation for Flowlytics (the fictional B2B SaaS whose
support docs Fishly answers from).

Hybrid approach (ADR-008): `spec.py` holds a deterministic skeleton — every
document, version, date, error code, and planted stale-data conflict is
declared in code — while `prose.py` fills the body text with an LLM and
caches it to disk. Structure is reproducible; prose is realistic.
"""
