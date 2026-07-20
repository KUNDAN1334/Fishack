# Fishly API image.
# PRODUCTION NOTE: a real build would be multi-stage (builder + slim runtime),
# pin a lockfile, and run as a non-root user. Kept minimal for learnability.
FROM python:3.12-slim

WORKDIR /srv/fishly

# Install deps first so code-only changes reuse the pip layer cache
COPY pyproject.toml ./
COPY app ./app
COPY fishnet ./fishnet
RUN pip install --no-cache-dir .

COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
