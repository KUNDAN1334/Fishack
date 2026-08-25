# Fishack API image.
#
# PRODUCTION NOTE: a real build would be multi-stage (builder + slim runtime),
# pin a lockfile, and run as a non-root user. Kept minimal for learnability.
FROM python:3.12-slim

WORKDIR /srv/fishack

# Install deps first so code-only changes reuse the pip layer cache
COPY pyproject.toml ./
COPY app ./app
COPY fishnet ./fishnet
RUN pip install --no-cache-dir .

COPY scripts ./scripts

# --------------------------------------------------------------------------
# Bake the embedding model into the image.
#
# This is the difference between a usable free-tier deployment and an unusable
# one. Without it, the container fetches ~130MB from Hugging Face on every cold
# start — and on a scale-to-zero host, "cold start" means every time someone
# opens /try after an idle period. Baking it in turns a ~45s first request into
# roughly 8s, and removes a hard dependency on huggingface.co being reachable
# from the host at boot.
#
# HF_HOME must be set as ENV (not ARG) so the runtime finds the same cache the
# build populated.
# --------------------------------------------------------------------------
ENV HF_HOME=/opt/hf
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('BAAI/bge-small-en-v1.5')"

# With the model already on disk, skip the Hub round-trips entirely. Those are
# the ~15 HEAD requests visible in the startup log; offline mode removes several
# seconds from every boot.
#
# The tradeoff, stated because it bites hard: if anything is NOT in the baked
# cache, startup fails instead of silently downloading. That is the correct
# direction — a missing model should fail the deploy, not the first customer —
# but it means enabling the reranker requires adding it to the RUN above.
ENV HF_HUB_OFFLINE=1

# --------------------------------------------------------------------------
# Cloud Run, Koyeb and most PaaS inject the port to listen on. Defaulting to
# 8000 keeps docker-compose working unchanged, where nothing sets PORT.
#
# `sh -c` is required for ${PORT} to be expanded — the exec form of CMD does no
# variable substitution, so the JSON-array version would try to bind to the
# literal string "${PORT}".
# --------------------------------------------------------------------------
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
