"use client";

/**
 * The right-hand "On this page" rail.
 *
 * Headings are read out of the rendered DOM rather than declared alongside the
 * page. That is the whole design decision here: a hand-maintained anchor list
 * and the document it indexes drift apart within a couple of edits, and a table
 * of contents pointing at a heading that no longer exists is worse than none —
 * it silently sends the reader to the wrong section.
 *
 * Scroll-spy uses IntersectionObserver with a top-weighted root margin rather
 * than a scroll handler. The margin (`-88px 0px -70% 0px`) means a heading
 * counts as "current" from the moment it clears the sticky header until it
 * leaves the top 30% of the viewport — which matches where a reader's eye
 * actually is, and stops the highlight flickering between two headings on a
 * short section.
 */

import { useEffect, useState } from "react";

interface Heading {
  id: string;
  text: string;
  level: 2 | 3;
}

export default function OnThisPage({ containerId = "doc-content" }: { containerId?: string }) {
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const container = document.getElementById(containerId);
    if (!container) return;

    const found = Array.from(container.querySelectorAll<HTMLElement>("h2[id], h3[id]")).map(
      (element) => {
        // Read the text from a CLONE with the "#" permalink removed. Reading the
        // live node would put a stray "#" on the end of every entry, and
        // removing it from the live node would delete the permalink itself.
        //
        // `textContent` rather than `innerText`: a heading may contain an inline
        // `<code>`, and we want the code's text, not its styling.
        const clone = element.cloneNode(true) as HTMLElement;
        clone.querySelectorAll("[data-heading-anchor]").forEach((node) => node.remove());
        return {
          id: element.id,
          text: (clone.textContent ?? "").trim(),
          level: element.tagName === "H2" ? (2 as const) : (3 as const),
        };
      },
    );
    setHeadings(found);
    if (found.length > 0) setActiveId(found[0].id);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-88px 0px -70% 0px", threshold: 0 },
    );

    found.forEach((heading) => {
      const element = document.getElementById(heading.id);
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
    // Re-runs on navigation because the container is remounted per route.
  }, [containerId]);

  if (headings.length < 2) return null;

  return (
    <nav aria-label="On this page" className="text-sm">
      <p className="mb-2 text-2xs font-semibold uppercase tracking-[0.12em] text-slate-400">
        On this page
      </p>
      <ul className="space-y-px border-l border-line">
        {headings.map((heading) => {
          const active = heading.id === activeId;
          return (
            <li key={heading.id}>
              <a
                href={`#${heading.id}`}
                aria-current={active ? "location" : undefined}
                className={`-ml-px block border-l py-1 transition-colors ${
                  heading.level === 3 ? "pl-6" : "pl-3"
                } ${
                  active
                    ? "border-ocean-500 font-medium text-ocean-700"
                    : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-900"
                }`}
              >
                {heading.text}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
