import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/deployment")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

const CHECKLIST = [
  "CREATE EXTENSION vector on the remote database",
  "python scripts/migrate.py against DATABASE_URL",
  "Corpus seeded — verify SELECT count(*) FROM chunks WHERE is_current returns 312",
  "REDIS_URL uses rediss:// (Upstash requires TLS)",
  "RERANKER_ENABLED=false if the host has under ~2 GB",
  "API keys set as secrets, never committed",
  "/admin protected with a token, or unreachable",
  "API_ORIGIN set on the frontend host",
  "/health returns pgvector_installed: true",
  "One real question answered end to end, with citations",
];

export default function DeploymentPage() {
  return (
    <DocPage
      href="/docs/deployment"
      eyebrow="Operations"
      title="Deployment"
      lead="Memory is the whole problem, and every hosting choice below follows from it. This application runs two local transformer models, which is unusual for a web service and does not fit in the 512 MB most free tiers offer."
    >
      <H2 id="memory">Read this first</H2>
      <DataTable
        columns={[
          { key: "component", header: "Component", width: "w-[46%]" },
          { key: "mem", header: "Resident memory", numeric: true },
        ]}
        rows={[
          { id: "torch", cells: { component: "PyTorch runtime", mem: "700 MB – 1 GB" } },
          { id: "bge", cells: { component: "bge-small-en-v1.5 (embeddings)", mem: "~130 MB" } },
          { id: "rr", cells: { component: "bge-reranker-base (cross-encoder)", mem: "~280 MB" } },
          { id: "api", cells: { component: "FastAPI + asyncpg + Redis client", mem: "~100 MB" } },
          { id: "total", cells: { component: <strong>Realistic total</strong>, mem: "1.5 – 2 GB" }, highlight: true },
        ]}
      />

      <Callout kind="caution" title="Most free PaaS tiers give you 512 MB">
        <p>
          So the default configuration does not fit, and pretending otherwise wastes an afternoon.
          There are exactly two honest ways forward.
        </p>
      </Callout>

      <H2 id="path-a">Path A — drop the reranker</H2>
      <CodeBlock language="shell" code={`RERANKER_ENABLED=false`} />
      <p>
        Resident memory falls to roughly 1&ndash;1.2 GB, and p95 latency drops from about five
        seconds to well under one.
      </p>

      <Callout kind="result" title="This is not a compromise — it is what the measurements say to do">
        <p>
          Vector-only has the <strong>better recall@5</strong> on this corpus (0.938 against 0.915).
          The reranker buys +0.073 MRR for +3.3 seconds, which is obviously wrong on a
          memory-constrained free tier and obviously right on a GPU. Being able to point at the
          measurement that justifies the deployment choice is a stronger position than deploying the
          heavier configuration would have been.
        </p>
      </Callout>

      <Callout kind="production" title="The real fix is not dropping the reranker">
        <p>
          It is replacing PyTorch with ONNX Runtime, which cuts the runtime from roughly 800 MB to
          roughly 100 MB and would fit <em>both</em> models in 512 MB. That is a genuine code change
          to the encoder and reranker modules — and both already sit behind narrow interfaces
          specifically so a swap like this stays local.
        </p>
      </Callout>

      <H2 id="path-b">Path B — a host with real memory</H2>
      <p>
        Hugging Face Spaces&apos; free CPU tier offers 2 vCPU and 16 GB of RAM, because it is built
        for exactly this kind of model-loading workload. Everything runs, reranker included.
      </p>
      <ul>
        <li>
          Free Spaces <strong>sleep after 48 hours of inactivity</strong>. Waking one reloads both
          models — a 30&ndash;60 second first request.
        </li>
        <li>
          There is active community concern about the free CPU tier and Docker SDK access for unpaid
          accounts. <strong>Verify the current terms before depending on it.</strong>
        </li>
      </ul>

      <H2 id="stack">The free-tier stack</H2>
      <DataTable
        columns={[
          { key: "piece", header: "Piece", width: "w-[24%]" },
          { key: "service", header: "Service" },
          { key: "why", header: "Why" },
        ]}
        rows={[
          {
            id: "pg",
            cells: {
              piece: "Postgres + pgvector",
              service: "Neon or Supabase",
              why: "The whole corpus is ~30 MB — nowhere near any free-tier limit",
            },
          },
          {
            id: "redis",
            cells: {
              piece: "Redis",
              service: "Upstash",
              why: "The answer cache. The app degrades gracefully without it, so exhausting the command quota is survivable",
            },
          },
          {
            id: "api",
            cells: {
              piece: "Backend",
              service: "HF Spaces (Path B), or Fly.io / Koyeb (Path A)",
              why: "Memory is the deciding factor, and it decides this row",
            },
            highlight: true,
          },
          {
            id: "fe",
            cells: {
              piece: "Frontend",
              service: "Vercel",
              why: "Next.js's native host, and the rewrite proxy works unchanged",
            },
          },
        ]}
      />

      <H2 id="steps">Step by step</H2>

      <H3 id="db">1 · Database</H3>
      <CodeBlock
        language="shell"
        code={`export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/fishack?sslmode=require"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
python scripts/migrate.py`}
      />

      <H3 id="seed">2 · Seed from your machine, not the server</H3>
      <p>
        Ingestion needs the embedding model and about two minutes of CPU. Doing that on a
        memory-constrained host is the slowest and most fragile part of any deployment, so run it
        locally against the remote database — or dump and restore, which avoids re-embedding
        entirely.
      </p>
      <CodeBlock
        language="shell"
        code={`# from your laptop, where the model already is
DATABASE_URL="postgresql://…neon.tech/fishack?sslmode=require" python scripts/ingest.py run

# or, faster
pg_dump "postgresql://fishack:fishack@localhost:5432/fishack" \\
  --no-owner --no-privileges -Fc -f fishack.dump
pg_restore -d "$DATABASE_URL" --no-owner --no-privileges fishack.dump`}
      />
      <p>
        Embeddings are deterministic and stored in the embedding cache, so the restored database is
        byte-identical to the local one.
      </p>

      <H3 id="redis-step">3 · Redis</H3>
      <CodeBlock language="shell" code={`REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379`} />
      <p>
        Note <code>rediss://</code> — Upstash requires TLS. The free command allowance is finite and
        the cache spends it on every request, but every Redis call is wrapped, so exhausting the
        quota degrades to a permanent cache miss rather than an outage.
      </p>

      <H3 id="backend">4 · Backend</H3>
      <p>
        On Spaces, use the Docker SDK and set <code>DATABASE_URL</code>, <code>REDIS_URL</code> and{" "}
        <code>GROQ_API_KEY</code> as <strong>secrets</strong>, not public variables. The Space port
        is 7860, so either expose that in the Dockerfile or declare the app port in the Space
        front-matter. On Fly.io or Koyeb, build the same Dockerfile with{" "}
        <code>RERANKER_ENABLED=false</code> and at least 1 GB.
      </p>
      <CodeBlock language="shell" code={`curl https://your-backend-url/health`} />

      <H3 id="frontend">5 · Frontend</H3>
      <p>
        Import the repository, set the root directory to <code>frontend</code>, and add one
        environment variable:
      </p>
      <CodeBlock language="shell" code={`API_ORIGIN=https://your-backend-url`} />
      <p>
        That is all. The Next config rewrites <code>/api/*</code> onto that origin, so the browser
        still sees a single origin and <strong>there is no CORS to configure</strong> — the same
        reason the proxy exists locally.
      </p>

      <H2 id="expectations">What a free-tier deployment will actually feel like</H2>
      <p>Say this out loud rather than letting someone discover it.</p>
      <DataTable
        columns={[
          { key: "thing", header: "", width: "w-[24%]" },
          { key: "reality", header: "Reality" },
        ]}
        rows={[
          {
            id: "cold",
            cells: {
              thing: <strong>Cold start</strong>,
              reality: "30–60s after the host sleeps — both models reload. An idle Neon project also suspends",
            },
          },
          {
            id: "first",
            cells: { thing: <strong>First query</strong>, reality: "Slow even when warm, if the cache is empty" },
          },
          {
            id: "quota",
            cells: {
              thing: <strong>LLM quota</strong>,
              reality:
                "Groq's free tier has a low tokens-per-minute ceiling. Under any real concurrency the fallback chain will fire — which is the resilience pattern working, and it is visible on the dashboard",
            },
            highlight: true,
          },
          {
            id: "cost",
            cells: {
              thing: <strong>Cost</strong>,
              reality: "$0. Every figure on the dashboard is virtual cost — what the usage would cost at paid-API prices",
            },
          },
        ]}
      />

      <H3 id="keepalive">Keeping it awake</H3>
      <p>
        A scheduled ping every thirty minutes stops the Space sleeping and the database suspending.
        Check the host&apos;s terms first — some free tiers consider it abuse. And it does not make
        a deployment production-grade; it makes a demonstration reliable enough to show someone.
      </p>
      <CodeBlock
        language="yaml"
        filename=".github/workflows/keepalive.yml"
        code={`name: keepalive
on:
  schedule: [{ cron: "*/30 * * * *" }]
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -sf \${{ secrets.BACKEND_URL }}/health || true`}
      />

      <H2 id="before-public">Before you make it public</H2>
      <Callout kind="caution" title="Two things are not production-safe by default">
        <p>
          <strong>The statistics endpoint reads across tenants.</strong> With no token set it is
          open. Set one, block it at the edge, or do not deploy the dashboard.
        </p>
        <p>
          <strong>The tenant switcher is a UI control, not an auth boundary.</strong> The tenant id
          arrives in the request body, which is correct for a demonstration with no login and a
          trivial cross-tenant read in production. It would come from an authenticated session
          instead, and the pipeline below would not change.
        </p>
      </Callout>

      <H2 id="checklist">Deployment checklist</H2>
      <ul className="!mt-4 !space-y-1.5 !pl-0" style={{ listStyle: "none" }}>
        {CHECKLIST.map((item) => (
          <li key={item} className="flex items-start gap-2.5 text-sm text-slate-700">
            <span
              aria-hidden="true"
              className="mt-[0.35rem] h-3.5 w-3.5 shrink-0 rounded-sm border border-line-strong bg-surface"
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <p className="!mt-8">
        <Link href="/docs/api">The API reference →</Link>
      </p>
    </DocPage>
  );
}
