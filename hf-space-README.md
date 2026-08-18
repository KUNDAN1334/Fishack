---
title: Fishack
emoji: 🎣
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# Fishack — API

Backend for [Fishack](https://github.com/YOUR_USERNAME/fishack): a multi-tenant
RAG customer support assistant with hybrid retrieval, a confidence gate,
grounded generation with verified citations, and a first-class eval harness.

**This Space runs the API only.** The chat UI is deployed separately on Vercel
and proxies here.

## Required Space secrets

| secret | notes |
|---|---|
| `DATABASE_URL` | Postgres + pgvector, e.g. Neon. Must end `?sslmode=require` |
| `REDIS_URL` | Upstash, `rediss://` (TLS) |
| `GROQ_API_KEY` | free tier; the only required LLM key |
| `ADMIN_TOKEN` | guards `/admin/*`, which reads across tenants |

## Health check

`GET /health` reports Postgres, pgvector, Redis and the active LLM chain.

Free CPU Spaces sleep after inactivity; the first request afterwards reloads
both local models and takes 30–60 seconds.
