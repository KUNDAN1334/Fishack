/**
 * The documentation map.
 *
 * One array, and everything navigational is derived from it: the sidebar, the
 * previous/next footer on every page, the mobile menu, and the search filter.
 * Adding a page means adding an entry here and a `page.tsx` — there is no
 * second place to remember.
 *
 * What is deliberately NOT here: the headings inside each page. Those are read
 * out of the rendered DOM by `OnThisPage`, because a hand-maintained list of
 * anchors drifts from the document it indexes within about two edits, and a
 * table of contents pointing at a heading that no longer exists is worse than
 * no table of contents.
 */

export interface DocPageMeta {
  /** Route. `/` is the overview, which doubles as the landing page. */
  href: string;
  /** Sidebar label. Short — this is a 240px column. */
  title: string;
  /** One line, shown in the mobile menu, on index cards, and as `<meta>`. */
  summary: string;
}

export interface DocGroup {
  title: string;
  pages: DocPageMeta[];
}

export const DOC_GROUPS: DocGroup[] = [
  {
    title: "Start here",
    pages: [
      {
        href: "/",
        title: "Overview",
        summary:
          "What Fishack is, the failure mode it was built against, and how each defence maps to something you can see in the UI.",
      },
      {
        href: "/docs/quickstart",
        title: "Quickstart",
        summary:
          "Three commands to a running stack with the corpus ingested, and what each one is actually doing.",
      },
      {
        href: "/docs/guided-tour",
        title: "Guided tour",
        summary:
          "Five queries in a fixed order, each one turning on a defence the previous one did not need.",
      },
    ],
  },
  {
    title: "Architecture",
    pages: [
      {
        href: "/docs/architecture",
        title: "System architecture",
        summary:
          "The components, the storage layout, the process boundaries, and where every tuning knob lives.",
      },
      {
        href: "/docs/query-path",
        title: "The query path",
        summary:
          "Eight stages from request to response, every exit path, and the streaming contract the UI depends on.",
      },
      {
        href: "/docs/ingestion",
        title: "Ingestion and chunking",
        summary:
          "Three loaders, three chunking strategies, content-hash dedup, versioning, and the second pass that tags conflicts.",
      },
      {
        href: "/docs/retrieval",
        title: "Retrieval and ranking",
        summary:
          "The keyword leg, the vector leg, reciprocal rank fusion, and a cross-encoder that costs more than the latency budget.",
      },
      {
        href: "/docs/generation",
        title: "Generation and citations",
        summary:
          "The confidence gate, the closed-book prompt, post-hoc citation validation, and three abstention paths with one exit.",
      },
      {
        href: "/docs/caching",
        title: "Caching",
        summary:
          "An exact cache, a semantic cache that is the most dangerous component in the system, and the two guardrails that make it survivable.",
      },
      {
        href: "/docs/tenant-isolation",
        title: "Tenant isolation",
        summary:
          "Four independent layers, a threat model, and a leakage test with controls that stop it passing vacuously.",
      },
    ],
  },
  {
    title: "Evaluation",
    pages: [
      {
        href: "/docs/evaluation",
        title: "The eval harness",
        summary:
          "A 65-case golden set, stable locators, four metrics with hand-checkable arithmetic, an LLM judge, and a CI regression gate.",
      },
      {
        href: "/docs/results",
        title: "Measured results",
        summary:
          "Every number this project claims, the command that reproduces it, and the caveat that limits it.",
      },
    ],
  },
  {
    title: "Operations",
    pages: [
      {
        href: "/docs/operations",
        title: "Running and operating",
        summary:
          "The dashboard's four questions, the failure table, service objectives, and what to do when each alarm fires.",
      },
      {
        href: "/docs/deployment",
        title: "Deployment",
        summary:
          "Memory is the whole problem. Two honest paths, the free-tier stack, and the checklist before anything is public.",
      },
      {
        href: "/docs/api",
        title: "API reference",
        summary:
          "Every endpoint, every schema, the SSE event contract, and the error taxonomy.",
      },
      {
        href: "/docs/configuration",
        title: "Configuration",
        summary:
          "Every environment variable and tuning knob, with its value, its provenance, and whether it was measured or guessed.",
      },
    ],
  },
  {
    title: "Reference",
    pages: [
      {
        href: "/docs/decisions",
        title: "Decision record",
        summary:
          "Twenty-eight ADRs: context, decision, alternatives considered, and why each was rejected.",
      },
      {
        href: "/docs/field-notes",
        title: "Field notes",
        summary:
          "Seven bugs that kept the test suite green while breaking the system, as expected → observed → root cause.",
      },
      {
        href: "/docs/limitations",
        title: "Limitations",
        summary:
          "What this system does not do, what the numbers do not support, and what would have to change.",
      },
      {
        href: "/docs/glossary",
        title: "Glossary",
        summary:
          "Every term this documentation uses in a specific sense, defined once.",
      },
    ],
  },
];

/** Flat reading order, used for the previous/next footer. */
export const DOC_ORDER: DocPageMeta[] = DOC_GROUPS.flatMap((group) => group.pages);

export function findDoc(href: string): DocPageMeta | undefined {
  return DOC_ORDER.find((page) => page.href === href);
}

/**
 * The pages either side of `href` in reading order.
 *
 * Returned as a pair rather than two lookups so a page cannot render a "next"
 * link that disagrees with its neighbour's "previous" link.
 */
export function neighbours(href: string): { prev?: DocPageMeta; next?: DocPageMeta } {
  const index = DOC_ORDER.findIndex((page) => page.href === href);
  if (index === -1) return {};
  return { prev: DOC_ORDER[index - 1], next: DOC_ORDER[index + 1] };
}
