"""Ingestion pipeline (Design.md §3 and §4).

    load -> dedup -> chunk (per-source strategy) -> embed -> upsert -> version

    models.py      shared types (ParsedDocument, ProtoChunk)
    tokenizer.py   token counting, matched to the embedding model
    loaders.py     three source formats -> ParsedDocument
    chunkers/      three strategies, one per source type
    dedup.py       content hashing
    versioning.py  supersession / is_current handling
    repository.py  all SQL writes
    pipeline.py    the orchestrator
"""
