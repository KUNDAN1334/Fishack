/**
 * The running product's shell — `/try` and `/admin`.
 *
 * Fixed to the viewport rather than scrolling the page: the assistant has two
 * independently scrolling columns (conversation and sources) and a composer
 * pinned to the bottom, none of which work if the document itself scrolls.
 *
 * `min-h-0` on the main element is load-bearing and easy to lose in a refactor.
 * Without it, a flex child refuses to shrink below its content, so the inner
 * scroll areas grow the page instead of scrolling — the symptom is a composer
 * that walks off the bottom of the screen as the conversation gets longer.
 */

import AppHeader from "@/components/site/AppHeader";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <main id="main" className="min-h-0 flex-1">
        {children}
      </main>
    </div>
  );
}
