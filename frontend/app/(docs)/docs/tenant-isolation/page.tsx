import type { Metadata } from "next";
import Link from "next/link";

import Callout from "@/components/docs/Callout";
import CodeBlock from "@/components/docs/CodeBlock";
import DataTable from "@/components/docs/DataTable";
import DocPage from "@/components/docs/DocPage";
import Steps from "@/components/docs/Steps";
import { H2, H3 } from "@/components/docs/Prose";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/tenant-isolation")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

export default function IsolationPage() {
  return (
    <DocPage
      href="/docs/tenant-isolation"
      eyebrow="Architecture"
      title="Tenant isolation"
      lead="The requirement is not 'remember to filter by tenant'. It is that a developer cannot write the unsafe query — the failure mode being defended against is silent, and a leak that nobody notices is the only kind that matters."
    >
      <H2 id="core">One object may read the corpus</H2>
      <p>
        <code>TenantScope</code> is the only thing in the codebase permitted to read the{" "}
        <code>chunks</code> table. A retrieval leg supplies a <em>fragment</em> — a projection, a
        predicate and an ordering — and the scope composes the real SQL:
      </p>

      <CodeBlock
        language="sql"
        filename="composed by app/retrieval/tenant_scope.py"
        code={`SELECT <leg projection>
FROM chunks c
WHERE c.tenant_id = $1          -- welded on, unconditionally, by the scope
  AND c.is_current              -- archived versions are never retrievable
  AND (<leg predicate>)         -- leg parameters start at $2
ORDER BY <leg ordering>
LIMIT $n`}
      />

      <p>
        <code>$1</code> belongs to the scope and is bound by it. Functions in the retrieval layer
        take a <code>TenantScope</code>, never a <code>tenant_id: str</code> — so there is no
        signature that would even accept an unscoped read, and the unsafe query is unwritable rather
        than discouraged.
      </p>

      <H2 id="layers">Four layers, weakest to strongest</H2>
      <Steps
        variant="numbered"
        steps={[
          {
            title: "Composition",
            aside: "structural",
            body: (
              <>
                The leg never writes <code>FROM</code> and never writes the tenant predicate. It
                cannot omit what it does not author.
              </>
            ),
          },
          {
            title: "Fragment guards, at construction time",
            aside: "__post_init__",
            body: (
              <>
                A leg query is rejected outright if its fragment mentions <code>tenant_id</code>,{" "}
                <code>is_current</code>, <code>$1</code>, a semicolon, or <code>FROM chunks</code>.
                This fires when the object is built, so an unsafe leg blows up in the first test
                that constructs it rather than in production.
              </>
            ),
          },
          {
            title: "Runtime tripwire",
            aside: "raises",
            body: (
              <>
                Every returned row&apos;s tenant is re-checked, and a mismatch raises.{" "}
                <strong>It raises rather than filtering</strong> — dropping the offending rows and
                continuing would serve a slightly-wrong result set that nobody notices. A leak
                Python quietly corrects is a leak nobody investigates. Crashing produces an incident,
                which produces a fix.
              </>
            ),
          },
          {
            title: "Source lint",
            aside: "a test",
            body: (
              <>
                A test greps the retrieval package and asserts that <code>FROM chunks</code> appears
                in exactly one file. This is the layer that survives a refactor by someone who never
                read this page.
              </>
            ),
          },
        ]}
      />

      <H2 id="alternatives">What was considered instead</H2>
      <DataTable
        columns={[
          { key: "option", header: "Option", width: "w-[28%]" },
          { key: "verdict", header: "Verdict" },
        ]}
        rows={[
          {
            id: "convention",
            cells: {
              option: "Convention plus code review",
              verdict:
                "What most codebases do, and it works until the one pull request that adds a quick debug query. The whole point is that the failure is silent",
            },
          },
          {
            id: "decorator",
            cells: {
              option: "A decorator on leg functions",
              verdict: "Nothing stops a developer from not applying it",
            },
          },
          {
            id: "rls",
            cells: {
              option: "Postgres row-level security",
              verdict:
                "Strictly better, and orthogonal rather than alternative — see below",
            },
            highlight: true,
          },
        ]}
      />

      <Callout kind="production" title="Row-level security belongs underneath all of this">
        <p>
          <code>ALTER TABLE chunks ENABLE ROW LEVEL SECURITY</code> with a policy over{" "}
          <code>current_setting(&apos;app.tenant_id&apos;)</code>, set per request. Then raw psql
          sessions and any future non-Python consumer are covered too, and the scope becomes a
          convenience rather than the only thing standing between two customers. It is noted in the
          initial migration&apos;s closing comment, where the next person to touch the schema will
          see it.
        </p>
      </Callout>

      <H2 id="cache-and-prompt">Isolation is not only a database concern</H2>
      <DataTable
        columns={[
          { key: "surface", header: "Surface", width: "w-[24%]" },
          { key: "how", header: "How it is scoped" },
        ]}
        rows={[
          {
            id: "db",
            cells: {
              surface: "Every corpus read",
              how: "Through the scope, with the predicate welded on and every row re-checked",
            },
          },
          {
            id: "cache",
            cells: {
              surface: "Answer cache",
              how: "Every key is namespaced by tenant, on both the exact and the semantic path",
            },
          },
          {
            id: "history",
            cells: {
              surface: "Conversation history",
              how: "Switching tenant clears the conversation. Carrying it across would feed one tenant's answers into another's prompt as context — not a chunk leak, but a leak",
            },
            highlight: true,
          },
          {
            id: "admin",
            cells: {
              surface: "The operations dashboard",
              how: "The one endpoint that deliberately reads ACROSS tenants, and therefore the one that needs its own authentication before anything is public",
            },
          },
        ]}
      />

      <H2 id="testing">Testing a negative</H2>
      <p>
        The leakage test seeds both tenants with <em>near-identical</em> content, so the tenant
        predicate is the only thing separating them, plants a secret in tenant B, and asserts tenant
        A never sees it.
      </p>
      <p>
        Every assertion is paired with a <strong>control</strong> proving that the thing whose
        absence is being asserted was actually present and findable. A leakage test that passes
        because the index was empty is worse than no test at all, because it retires the question.
      </p>

      <Callout kind="caution" title="The control itself once passed vacuously">
        <p>
          The control counted text-search matches across the <em>whole</em> chunks table. The real
          two-tenant corpus satisfied it, while the synthetic test tenants matched nothing at all —
          so the test was green and proving nothing. A control must be scoped as tightly as the
          thing it vouches for. It now asserts that <em>both</em> test tenants are reachable by the
          query. <Link href="/docs/field-notes#control">The full story is field note 3.</Link>
        </p>
      </Callout>

      <H2 id="threat-model">What this does and does not defend against</H2>
      <DataTable
        columns={[
          { key: "threat", header: "Threat", width: "w-[34%]" },
          { key: "status", header: "Status" },
        ]}
        rows={[
          {
            id: "forgot",
            cells: {
              threat: "A developer forgets the tenant filter",
              status: "Defended, structurally — the query is unwritable",
            },
          },
          {
            id: "refactor",
            cells: {
              threat: "A refactor introduces a new read path",
              status: "Defended by the source lint and the fragment guards",
            },
          },
          {
            id: "row",
            cells: {
              threat: "A bug returns a foreign row anyway",
              status: "Detected at runtime, and it raises rather than filtering",
            },
          },
          {
            id: "prompt",
            cells: {
              threat: "Cross-tenant context via conversation history",
              status: "Defended — switching clears the conversation, and the UI says so first",
            },
          },
          {
            id: "auth",
            cells: {
              threat: "A client asserting a tenant it does not own",
              status:
                "NOT defended. The tenant arrives in the request body, which is correct for a demonstration with no login and a trivial cross-tenant read in production",
            },
            highlight: true,
          },
          {
            id: "sql",
            cells: {
              threat: "Raw SQL sessions, or a future non-Python consumer",
              status: "Not covered. This is what row-level security would add",
            },
          },
          {
            id: "admin-threat",
            cells: {
              threat: "The admin statistics endpoint",
              status:
                "Reads across tenants by design. Protect it with a token, block it at the edge, or do not deploy it",
            },
          },
        ]}
      />

      <Callout kind="caution" title="The tenant switcher is a UI control, not an auth boundary">
        <p>
          The tenant id arrives in the request body and is validated against the tenants table — so
          a typo produces a 404 rather than an empty result set that reads as &ldquo;we have no
          documentation about that&rdquo;. In a real deployment it would come from the authenticated
          session or a JWT claim and never be accepted from the client. The scope would be
          constructed from the auth context instead; nothing below it in the pipeline changes, which
          is the point of putting the boundary there. The note lives in the route&apos;s docstring
          as well as here.
        </p>
      </Callout>
    </DocPage>
  );
}
