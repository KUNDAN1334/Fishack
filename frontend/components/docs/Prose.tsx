/**
 * Prose primitives.
 *
 * Documentation pages are written as TSX rather than MDX. That trade is
 * deliberate: MDX would give slightly nicer authoring for paragraphs, and would
 * cost a build plugin, a second syntax to keep valid, and an escape hatch every
 * time a page needs a diagram, a metrics table or a callout — which on this
 * site is most sections. TSX means every block on every page is a typed
 * component, and a renamed prop breaks the build instead of rendering wrong.
 *
 * Headings take an explicit `id` because that id is a permanent anchor: it goes
 * in the "On this page" rail, in cross-page links, and in URLs people paste. An
 * auto-slugged heading changes its anchor the moment someone rewords the
 * heading, quietly breaking every link into it.
 */

import type { ReactNode } from "react";

/** A section heading. `id` is the permanent anchor — treat it as an API. */
export function H2({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="group scroll-mt-24">
      {children}
      {/* `data-heading-anchor` is a contract with OnThisPage, which strips this
          node before reading the heading's text. Without it every entry in the
          right-hand rail would end in a stray "#". */}
      <a
        href={`#${id}`}
        data-heading-anchor=""
        aria-label="Link to this section"
        className="ml-2 select-none text-ocean-300 opacity-0 transition-opacity
                   focus-visible:opacity-100 group-hover:opacity-100"
      >
        #
      </a>
    </h2>
  );
}

export function H3({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h3 id={id} className="scroll-mt-24">
      {children}
    </h3>
  );
}

/**
 * The standfirst under a page title. One paragraph, larger than body, and it
 * has to answer "why would I read this page" on its own.
 */
export function Lead({ children }: { children: ReactNode }) {
  return <p className="text-lg leading-relaxed text-slate-500">{children}</p>;
}

export function P({ children }: { children: ReactNode }) {
  return <p>{children}</p>;
}

export function UL({ children }: { children: ReactNode }) {
  return <ul>{children}</ul>;
}

export function OL({ children }: { children: ReactNode }) {
  return <ol>{children}</ol>;
}

export function LI({ children }: { children: ReactNode }) {
  return <li>{children}</li>;
}

/** Inline code. Use for identifiers, paths, config keys, error codes. */
export function C({ children }: { children: ReactNode }) {
  return <code>{children}</code>;
}

/**
 * An inline metric. Distinct from `<C>` because a number is not an identifier:
 * it gets tabular figures so that two of them in adjacent sentences line up,
 * and it never gets a border, which would make a number look clickable.
 */
export function Metric({ children }: { children: ReactNode }) {
  return <span className="figure font-medium text-slate-900">{children}</span>;
}

/**
 * A horizontal rule between major movements of a long page. Used sparingly —
 * an `H2` already creates a break, and a rule under every one turns the page
 * into a ladder.
 */
export function Divider() {
  return <hr className="!mt-14 border-line" />;
}
