import type { Metadata } from "next";

import AdrCard from "@/components/docs/AdrCard";
import Callout from "@/components/docs/Callout";
import DocPage from "@/components/docs/DocPage";
import { H2 } from "@/components/docs/Prose";
import { ADR_PHASES, ADRS } from "@/lib/adrs";
import { findDoc } from "@/lib/docs-nav";

const meta = findDoc("/docs/decisions")!;

export const metadata: Metadata = { title: meta.title, description: meta.summary };

/**
 * The decision record.
 *
 * Grouped by phase rather than listed by number, because build order is how the
 * decisions actually relate: several later entries exist only because an earlier
 * one closed off an option, and a numeric list hides that.
 */

export default function DecisionsPage() {
  return (
    <DocPage
      href="/docs/decisions"
      eyebrow="Reference"
      title="Decision record"
      lead="Thirty entries, each with the context, the decision, and the alternatives that were rejected with the reason. Entries are never rewritten once published — a superseded one gets a note, because the record is what was believed at the time and rewriting it destroys the only thing it is for."
    >
      <Callout kind="note" title="Why this format, and why every entry has alternatives">
        <p>
          &ldquo;We chose Postgres full-text search&rdquo; is a fact. &ldquo;We chose Postgres
          full-text search because a Python BM25 index lives in process memory and would put tenant
          filtering in application code after scoring&rdquo; is a decision — and it is the only form
          that helps the next person, who is usually you, six months later, wondering whether the
          obvious alternative was ever considered.
        </p>
        <p>
          Several of these record a decision that later turned out to be wrong, or that is still
          open. Those are the useful ones.
        </p>
      </Callout>

      {ADR_PHASES.map((phase) => {
        const entries = ADRS.filter((adr) => adr.phase === phase);
        if (entries.length === 0) return null;
        return (
          <section key={phase}>
            <H2 id={phase.toLowerCase().replace(/\s+/g, "-")}>{phase}</H2>
            <div className="!mt-4 space-y-2">
              {entries.map((adr) => (
                <AdrCard key={adr.id} adr={adr} />
              ))}
            </div>
          </section>
        );
      })}
    </DocPage>
  );
}
