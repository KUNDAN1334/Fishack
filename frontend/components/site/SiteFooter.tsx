/**
 * The documentation footer.
 *
 * Three columns of links plus the one sentence that has to survive being read
 * out of context: what this system is, and what it refuses to do. A recruiter
 * who scrolls to the bottom of one page and reads nothing else should still
 * leave knowing that.
 *
 * A server component — nothing here is interactive, so nothing here needs to
 * cost the client a hydration boundary.
 */

import Link from "next/link";
import { Wordmark } from "@/components/ui/Icon";

const COLUMNS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "Learn",
    links: [
      { href: "/", label: "Overview" },
      { href: "/docs/quickstart", label: "Quickstart" },
      { href: "/docs/guided-tour", label: "Guided tour" },
      { href: "/docs/query-path", label: "The query path" },
    ],
  },
  {
    title: "Evidence",
    links: [
      { href: "/docs/evaluation", label: "The eval harness" },
      { href: "/docs/results", label: "Measured results" },
      { href: "/docs/field-notes", label: "Field notes" },
      { href: "/docs/limitations", label: "Limitations" },
    ],
  },
  {
    title: "Reference",
    links: [
      { href: "/docs/api", label: "API reference" },
      { href: "/docs/configuration", label: "Configuration" },
      { href: "/docs/decisions", label: "Decision record" },
      { href: "/docs/glossary", label: "Glossary" },
    ],
  },
];

export default function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line bg-surface">
      <div className="mx-auto max-w-shell px-4 py-12 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <div>
            <div className="flex items-center gap-2.5">
              <Wordmark size={26} />
              <span className="text-[15px] font-semibold tracking-tight text-slate-900">Fishack</span>
            </div>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-slate-500">
              A multi-tenant RAG support assistant that answers only from a customer&apos;s own
              documentation — every claim cited, every citation verified, and an abstention
              instead of a guess when the corpus cannot support an answer.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.title}>
              <p className="mb-3 text-2xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                {column.title}
              </p>
              <ul className="space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-slate-600 transition-colors hover:text-ocean-700"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-line pt-6 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
          <p>
            Built without LangChain, LlamaIndex, or a vendor SDK. Retrieval, fusion, reranking,
            prompting, citation validation, caching and evaluation are written out.
          </p>
          <p className="figure shrink-0">
            Flowlytics is a fictional customer. Every figure is measured, and says where.
          </p>
        </div>
      </div>
    </footer>
  );
}
