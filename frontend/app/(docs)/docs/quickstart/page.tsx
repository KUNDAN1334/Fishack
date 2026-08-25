import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Steps from "@/components/docs/Steps";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/quickstart")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function QuickstartPage() {
  return (
    <DocPage
      href="/docs/quickstart"
      eyebrow="Start here"
      title="Quickstart"
      lead="Three commands bring up Postgres, Redis, the API and the UI together, and ingest a committed corpus. The whole path needs exactly one free API key, and the first run is deliberately slow."
    >
      <H2 id="three-commands">Three commands</H2>
      <CodeBlock
        language="shell"
        code={`cp .env.example .env    # add a free Groq key — the rest are optional fallbacks
docker compose up -d --build
docker compose exec api python scripts/ingest.py run`}
      />
      <p>
        Then open <code>http://localhost:3000</code> for the documentation and the assistant, and{" "}
        <code>http://localhost:3000/admin</code> for operations.
      </p>

      <Callout kind="note" title="Nothing here needs an API key to reproduce">
        <p>
          The corpus is <strong>committed to the repository</strong>, including the cached LLM prose
          used to generate it. A fresh clone reproduces byte-identical documents with no key at all.
          A key is needed only to <em>answer</em> questions, not to build the corpus or run the
          retrieval evaluation.
        </p>
      </Callout>

      <H2 id="what-each-step-does">What each step is actually doing</H2>
      <Steps
        steps={[
          {
            title: "One API key, and which one",
            aside: ".env",
            body: (
              <>
                Only one provider is required. Groq is the recommended primary — fastest inference
                and the most generous free daily request quota of the four. Gemini, OpenRouter and
                a local Ollama are optional fallbacks; the chain fails over automatically when one
                is rate-limited or exhausted.
              </>
            ),
          },
          {
            title: "First boot downloads two models, on purpose",
            aside: "~450 MB",
            body: (
              <>
                The API container fetches <code>bge-small-en-v1.5</code> (~130 MB) and{" "}
                <code>bge-reranker-base</code> (~280 MB) <strong>at startup</strong>, not on first
                request. Paying that during boot means the first user gets a normal response
                instead of a ten-second one, and a missing model fails the deploy rather than the
                first customer. Watch for{" "}
                <code>Fishack up. LLM chain: groq -&gt; …</code> in{" "}
                <code>docker compose logs -f api</code>.
              </>
            ),
          },
          {
            title: "Ingestion embeds the corpus",
            aside: "~312 chunks · ~2 min",
            body: (
              <>
                156 chunks per tenant across two tenants, embedded on CPU. The step is idempotent —
                documents are deduplicated by content hash, so re-running is nearly free. Verify
                with <code>scripts/ingest.py stats</code>.
              </>
            ),
          },
          {
            title: "Confirm before building anything on top",
            aside: "369 tests",
            body: (
              <>
                <code>scripts/smoke_test.py</code> checks Postgres, the pgvector extension, Redis
                and <em>every configured provider</em> with a real call, so a misconfigured
                provider surfaces here rather than three layers later.{" "}
                <code>pytest -q -m &quot;not integration&quot;</code> should report 369 passed.
              </>
            ),
          },
        ]}
      />

      <H2 id="providers">Providers and their free tiers</H2>
      <DataTable
        columns={[
          { key: "provider", header: "Provider" },
          { key: "where", header: "Where to get a key" },
          { key: "tier", header: "Free tier" },
        ]}
        rows={[
          {
            id: "groq",
            cells: {
              provider: "Groq",
              where: "console.groq.com → API Keys",
              tier: "Generous daily request quota, low tokens per minute",
            },
            note: "primary — first in the chain",
            highlight: true,
          },
          {
            id: "gemini",
            cells: {
              provider: "Gemini",
              where: "aistudio.google.com",
              tier: "Tight daily quota; good as a second hop",
            },
          },
          {
            id: "openrouter",
            cells: {
              provider: "OpenRouter",
              where: "openrouter.ai",
              tier: "`:free` model routes",
            },
          },
          {
            id: "ollama",
            cells: {
              provider: "Ollama",
              where: "local install",
              tier: "Fully offline, needs roughly 8 GB of RAM",
            },
          },
        ]}
        caption="Chain order is configuration, not code: LLM_PROVIDER_ORDER defaults to groq,gemini,openrouter,ollama."
      />

      <Callout kind="caution" title="A 404 from a provider is a config problem, not a bug">
        <p>
          Free-tier model lineups change constantly — Gemini retired its entire 2.5 line in July
          2026. Model names therefore live in configuration and never in code, so the fix is one
          line in <code>.env</code>. If a provider starts returning 404, update the model name
          before looking anywhere else.
        </p>
      </Callout>

      <H2 id="without-docker">Local development without Docker</H2>
      <p>
        A faster loop, with hot reload on both sides. Infrastructure stays in Docker; the API and
        the frontend run on the host.
      </p>
      <CodeBlock
        language="shell"
        code={`docker compose up -d postgres redis          # infrastructure only

python -m venv .venv
.venv/Scripts/activate                       # or: source .venv/bin/activate
pip install -e ".[dev]"
python scripts/migrate.py
python scripts/ingest.py run

make api                                     # terminal 1
cd frontend && npm install && npm run dev     # terminal 2`}
      />

      <Callout kind="note" title="ConnectionRefusedError on Windows">
        <p>
          <code>[WinError 1225]</code> means the Postgres container is not running. Start Docker
          Desktop and <code>docker compose up -d postgres redis</code>. Do <strong>not</strong>{" "}
          recreate the database — the <code>pgdata</code> volume is what persists your ingested
          corpus across restarts.
        </p>
      </Callout>

      <H2 id="tooling">The commands worth knowing</H2>
      <DataTable
        columns={[
          { key: "command", header: "Command", width: "w-[34%]" },
          { key: "what", header: "What it does" },
        ]}
        rows={[
          { id: "test", cells: { command: <code>make test</code>, what: "369 unit tests plus 23 integration tests" } },
          {
            id: "eval-retrieval",
            cells: {
              command: <code>make eval-retrieval</code>,
              what: "Retrieval scorecard across five arms. No LLM calls, under a minute, fully reproducible.",
            },
            highlight: true,
          },
          {
            id: "eval",
            cells: {
              command: <code>make eval</code>,
              what: "The full harness including LLM-as-judge, compared against the committed baseline",
            },
          },
          {
            id: "chunking",
            cells: {
              command: <code>make chunking-experiment</code>,
              what: "Naive fixed-window versus per-source chunking, on shadow tenants",
            },
          },
          { id: "tune", cells: { command: <code>make tune</code>, what: "Sweep the confidence gate against the golden set" } },
          {
            id: "playground",
            cells: {
              command: <code>make playground</code>,
              what: "BM25, vector, hybrid and reranked results side by side for one query",
            },
          },
          {
            id: "chat",
            cells: {
              command: <code>make chat</code>,
              what: "The pipeline in a terminal, with every stage's decision printed",
            },
          },
          { id: "prompt", cells: { command: <code>make show-prompt</code>, what: "The exact messages the model receives" } },
          {
            id: "triage",
            cells: {
              command: <code>make triage</code>,
              what: "Classify thumbs-down feedback into retrieval, generation or stale-data failures",
            },
          },
        ]}
      />

      <H3 id="next">Next</H3>
      <p>
        <Link href="/docs/guided-tour">The guided tour</Link> walks five queries in a fixed order,
        each one turning on a defence the previous one did not need. It is the fastest way to see
        what the system does, and it takes about three minutes.
      </p>
    </DocPage>
  );
}
