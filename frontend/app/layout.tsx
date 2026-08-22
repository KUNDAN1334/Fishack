import type { Metadata } from "next";
import "./globals.css";

/**
 * The root layout.
 *
 * Deliberately thin. It owns the document, the base metadata and the skip
 * link, and nothing else — because the site now has two genuinely different
 * chromes and neither should be squeezed into a shared header:
 *
 *   `app/(docs)`  documentation. Scrolls the page, sidebar, footer, wide.
 *   `app/(app)`   the running product. Fixed viewport height, inner panels
 *                 scroll, no footer, a tenant switcher in the composer.
 *
 * The previous version had one header for both, which is why the chat page
 * carried a marketing tagline and the docs had nowhere to put navigation.
 * Route groups let each own its frame without changing a single URL.
 *
 * `h-full` on both `html` and `body` is load-bearing for the product shell:
 * without it the app layout's `h-full` resolves against `auto` and the inner
 * scroll areas grow the page instead of scrolling.
 */

export const metadata: Metadata = {
  metadataBase: new URL("https://fishack.local"),
  title: {
    default: "Fishack — grounded, cited, confidence-gated support answers",
    template: "%s · Fishack",
  },
  description:
    "A multi-tenant RAG support assistant built without a RAG framework: hybrid retrieval, " +
    "post-hoc citation validation, a confidence gate that abstains instead of guessing, and an " +
    "evaluation harness that says when it is wrong.",
  openGraph: {
    title: "Fishack",
    description:
      "Every claim cited, every citation verified, confidence-gated — when it isn't sure it " +
      "escalates instead of guessing.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">
        {/* The keyboard path into a 19-page documentation site starts here.
            Visually hidden until focused, then a real, styled control. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50
                     focus:rounded-md focus:bg-ocean-600 focus:px-3 focus:py-2 focus:text-sm
                     focus:font-medium focus:text-white"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
