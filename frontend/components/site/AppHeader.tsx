"use client";

/**
 * The running product's header.
 *
 * A different object from `SiteHeader`, and the difference is the point. The
 * documentation header is a navigation surface for a stranger; this one is
 * chrome for someone using a tool. It is shorter, it carries no marketing
 * copy, and its only navigation is the pair of views the product actually has
 * — the assistant and the operations dashboard.
 *
 * The one thing it does carry is the promise, on `md` and up, because the whole
 * UI beneath it exists to make each clause of that sentence observable and a
 * reader deciding whether to trust an answer should be able to see what they
 * were promised without leaving the page.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ArrowLeft, Wordmark } from "@/components/ui/Icon";

const VIEWS = [
  { href: "/try", label: "Assistant" },
  { href: "/admin", label: "Operations" },
];

export default function AppHeader() {
  const pathname = usePathname();

  return (
    <header className="z-30 shrink-0 border-b border-line bg-surface">
      <div className="mx-auto flex h-14 max-w-shell items-center gap-3 px-4 sm:px-5">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="Fishack home">
          <Wordmark size={24} />
          <span className="text-sm font-semibold tracking-tight text-slate-900">Fishack</span>
        </Link>

        <p className="ml-3 hidden border-l border-line pl-4 text-xs leading-relaxed text-slate-500 md:block">
          Every claim cited, every citation verified, confidence-gated — when it isn&apos;t sure it
          escalates instead of guessing.
        </p>

        <nav aria-label="Views" className="ml-auto flex items-center gap-0.5 rounded-lg border border-line bg-surface-sunken p-0.5">
          {VIEWS.map((view) => {
            const active = pathname === view.href;
            return (
              <Link
                key={view.href}
                href={view.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1 text-sm transition-colors ${
                  active
                    ? "bg-surface font-medium text-slate-900 shadow-card"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {view.label}
              </Link>
            );
          })}
        </nav>

        <Link
          href="/"
          className="ml-1 hidden items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-slate-500
                     transition-colors hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
        >
          <ArrowLeft size={14} />
          Docs
        </Link>
      </div>
    </header>
  );
}
