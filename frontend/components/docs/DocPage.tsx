/**
 * The frame every documentation page renders inside.
 *
 * It owns the title block, the reading column, and the previous/next footer.
 * A page file is therefore nothing but its content — no page can accidentally
 * ship a different heading size, a different measure, or a footer that
 * disagrees with the sidebar's ordering, because none of them own those things.
 *
 * `id="doc-content"` on the article is a contract: `OnThisPage` scans inside it
 * for headings. If that id moves, the right-hand rail silently empties, so it
 * lives here rather than being repeated per page.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { ArrowLeft, ArrowRight } from "@/components/ui/Icon";
import { neighbours } from "@/lib/docs-nav";

export default function DocPage({
  href,
  eyebrow,
  title,
  lead,
  children,
}: {
  /** This page's own route — used to resolve its neighbours. */
  href: string;
  /** The group this page belongs to. Orients a reader who arrived by search. */
  eyebrow: string;
  title: string;
  lead: ReactNode;
  children: ReactNode;
}) {
  const { prev, next } = neighbours(href);

  return (
    <article id="doc-content" className="prose-doc max-w-prose pb-4">
      <header className="!mt-0 border-b border-line pb-7">
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ocean-600">
          {eyebrow}
        </p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <div className="mt-4 text-lg leading-relaxed text-slate-500">{lead}</div>
      </header>

      {children}

      {(prev || next) && (
        <nav
          aria-label="Documentation pagination"
          className="!mt-16 grid gap-3 border-t border-line pt-8 sm:grid-cols-2"
        >
          {prev ? (
            <Link
              href={prev.href}
              className="group rounded-lg border border-line bg-surface px-4 py-3 no-underline
                         transition-colors hover:border-ocean-300 hover:bg-ocean-50/40"
            >
              <span className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.1em] text-slate-400">
                <ArrowLeft size={12} />
                Previous
              </span>
              <span className="mt-1 block text-sm font-medium text-slate-900">{prev.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {next ? (
            <Link
              href={next.href}
              className="group rounded-lg border border-line bg-surface px-4 py-3 text-right no-underline
                         transition-colors hover:border-ocean-300 hover:bg-ocean-50/40"
            >
              <span className="flex items-center justify-end gap-1.5 text-2xs font-medium uppercase tracking-[0.1em] text-slate-400">
                Next
                <ArrowRight size={12} />
              </span>
              <span className="mt-1 block text-sm font-medium text-slate-900">{next.title}</span>
            </Link>
          ) : null}
        </nav>
      )}
    </article>
  );
}
