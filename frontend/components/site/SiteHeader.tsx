"use client";

/**
 * The documentation site's header.
 *
 * Two jobs, and the second one is the reason the information architecture
 * changed in this redesign:
 *
 *   1. Navigate the documentation.
 *   2. Get someone into the running product in one click.
 *
 * Documentation is now the front door — `/` is the overview, not the chat UI —
 * because the first thirty seconds a stranger spends here should explain what
 * the system is and what it proves. The live application sits behind a single
 * primary action, `Try it`, which lands on `/try` with the operations dashboard
 * one tab away from there.
 *
 * The mobile menu is a plain disclosure rather than a portal-based dialog: it
 * has no focus trap to get wrong, closes on route change, and works before
 * hydration if the page is opened with JavaScript still loading.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { DOC_GROUPS } from "@/lib/docs-nav";
import { ArrowRight, Close, Menu, Wordmark } from "@/components/ui/Icon";

/** The four destinations worth a top-level slot. Everything else is sidebar. */
const PRIMARY = [
  { href: "/docs/architecture", label: "Architecture" },
  { href: "/docs/evaluation", label: "Evaluation" },
  { href: "/docs/results", label: "Results" },
  { href: "/docs/decisions", label: "Decisions" },
];

export default function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the menu whenever the route changes. Without this, tapping a link
  // navigates underneath a menu that stays open over the new page.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-shell items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="Fishack documentation, home"
        >
          <Wordmark size={26} />
          <span className="text-[15px] font-semibold tracking-tight text-slate-900">Fishack</span>
          <span className="hidden text-2xs font-medium uppercase tracking-[0.14em] text-slate-400 sm:inline">
            Docs
          </span>
        </Link>

        <nav aria-label="Sections" className="ml-4 hidden items-center gap-0.5 lg:flex">
          {PRIMARY.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                  active
                    ? "bg-ocean-50 font-medium text-ocean-700"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/try"
            className="group inline-flex items-center gap-1.5 rounded-md bg-ocean-600 px-3 py-1.5
                       text-sm font-medium text-white shadow-card transition-colors hover:bg-ocean-700"
          >
            Try it
            <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
          </Link>

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="site-mobile-menu"
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 lg:hidden"
          >
            {menuOpen ? <Close size={18} title="Close menu" /> : <Menu size={18} title="Open menu" />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div
          id="site-mobile-menu"
          className="max-h-[70vh] overflow-y-auto border-t border-line bg-surface px-4 py-4 lg:hidden"
        >
          {DOC_GROUPS.map((group) => (
            <div key={group.title} className="mb-5 last:mb-0">
              <p className="mb-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                {group.title}
              </p>
              <ul className="space-y-0.5">
                {group.pages.map((page) => (
                  <li key={page.href}>
                    <Link
                      href={page.href}
                      className={`block rounded-md px-2 py-1.5 text-sm ${
                        pathname === page.href
                          ? "bg-ocean-50 font-medium text-ocean-700"
                          : "text-slate-600 hover:bg-slate-100"
                      }`}
                    >
                      {page.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </header>
  );
}
