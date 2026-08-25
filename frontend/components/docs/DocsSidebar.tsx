"use client";

/**
 * The documentation sidebar.
 *
 * Every page in the set, grouped, always expanded. There is no accordion: with
 * nineteen pages the whole tree fits in one column at this type size, and a
 * collapsed group hides exactly the page a reader was hoping to discover by
 * scanning. Progressive disclosure is for products with a hundred pages.
 *
 * The active item is marked with a left rule rather than a filled pill, so the
 * eye can find its place without the sidebar competing with the content column
 * for attention.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DOC_GROUPS } from "@/lib/docs-nav";

export default function DocsSidebar() {
  const pathname = usePathname();

  return (
    <nav aria-label="Documentation" className="text-sm">
      {DOC_GROUPS.map((group) => (
        <div key={group.title} className="mb-7 last:mb-0">
          <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.12em] text-slate-400">
            {group.title}
          </p>
          <ul className="space-y-px border-l border-line">
            {group.pages.map((page) => {
              const active = pathname === page.href;
              return (
                <li key={page.href}>
                  <Link
                    href={page.href}
                    aria-current={active ? "page" : undefined}
                    className={`-ml-px block border-l py-1.5 pl-3 transition-colors ${
                      active
                        ? "border-ocean-500 font-medium text-ocean-700"
                        : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
                    }`}
                  >
                    {page.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
