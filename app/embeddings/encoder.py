"""sentence-transformers wrapper for BAAI/bge-small-en-v1.5.

Two bge-specific details that are easy to get wrong and expensive to debug:

1. QUERY PREFIX. BGE models are trained with an asymmetric instruction:
   queries get prefixed with "Represent this sentence for searching relevant
   passages: ", passages get nothing. Skipping this costs a few points of
   retrieval quality — a silent degradation, since everything still "works".

2. NORMALIZATION. We L2-normalize embeddings so cosine similarity reduces to
   a dot product, and so pgvector's `<=>` cosine operator behaves
   consistently. Normalized vectors also make the semantic-cache threshold
   (0.95, Phase 5) meaningful across the board.

PRODUCTION NOTE: with a paid tier this would be text-embedding-3-large
(3072 dims, better on technical text, no local compute). We use bge-small
because it's free, CPU-viable, and 384 dims keeps the HNSW index small. The
retrieval CODE is identical either way — only the vector source changes.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# BGE's prescribed query instruction. Passages are embedded bare.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# Batch size for CPU encoding. 32 keeps memory modest on a laptop while
# still amortizing the per-batch overhead; larger batches show diminishing
# returns without a GPU.
DEFAULT_BATCH_SIZE = 32


class Encoder:
    """Loads the model once and encodes text to normalized float lists."""

    def __init__(self, model_name: str, batch_size: int = DEFAULT_BATCH_SIZE):
        from sentence_transformers import SentenceTransformer  # lazy: heavy import

        logger.info("loading embedding model %s (first run downloads ~130MB)", model_name)
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks (no instruction prefix)."""
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 200,
            convert_to_numpy=True,
        )
        return [vector.tolist() for vector in vectors]

    def encode_query(self, text: str) -> list[float]:
        """Embed a search query (WITH the BGE instruction prefix)."""
        return self.encode_passages([QUERY_INSTRUCTION + text])[0]


@lru_cache
def get_encoder(model_name: str, batch_size: int = DEFAULT_BATCH_SIZE) -> Encoder:
    """Process-wide singleton — loading the model takes several seconds and
    ~150MB of RAM; doing it per call would dominate ingestion time."""
    return Encoder(model_name, batch_size)
