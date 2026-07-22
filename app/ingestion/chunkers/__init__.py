"""Three chunking strategies, one per source type (Design.md §4).

    docs.py       structure-aware: split on headings, 300-500 tokens, 15% overlap
    changelog.py  entry-level: one changelog entry = one chunk
    tickets.py    conversation-level: one Q&A pair = one chunk

"Main ek single chunking strategy sab sources pe force nahi karta — kyunki
changelog ka atomic unit ek entry hai, jabki doc ka atomic unit ek section
hai." (Design.md §4). Phase 4 measures exactly how much this is worth
against a naive fixed-size baseline.
"""

from app.ingestion.chunkers.base import CHUNKER_REGISTRY, Chunker, get_chunker  # noqa: F401
