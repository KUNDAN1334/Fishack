/**
 * The documentation shell.
 *
 * A three-column reading frame: navigation on the left, one measured column of
 * content in the middle, section anchors on the right. Both rails are sticky
 * and independently scrollable; neither is ever taller than the viewport, so
 * the reader never loses their place in the tree while scrolling a long page.
 *
 * The measure is fixed at `max-w-prose` (~72ch at 15px) rather than filling the
 * available width. On a 27" monitor a full-width paragraph is unreadable, and
 * the space is better spent on the two rails and on diagrams, which are allowed
 * to break out of the measure and scroll horizontally.
 *
 * Rails collapse below `xl` and `lg` respectively; the sidebar's content is
 * reachable from the header's mobile menu, and the anchors are reachable by
 * scrolling, which is what a phone reader does anyway.
 */

import SiteFooter from "@/components/site/SiteFooter";
import SiteHeader from "@/components/site/SiteHeader";
import DocsSidebar from "@/components/docs/DocsSidebar";
import OnThisPage from "@/components/docs/OnThisPage";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <SiteHeader />

      <div className="mx-auto flex w-full max-w-shell flex-1 gap-10 px-4 sm:px-6">
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="thin-scroll sticky top-14 max-h-[calc(100vh-3.5rem)] overflow-y-auto py-10 pr-2">
            <DocsSidebar />
          </div>
        </aside>

        <main id="main" className="min-w-0 flex-1 py-10">
          {children}
        </main>

        <aside className="hidden w-52 shrink-0 xl:block">
          <div className="thin-scroll sticky top-14 max-h-[calc(100vh-3.5rem)] overflow-y-auto py-10 pl-2">
            <OnThisPage />
          </div>
        </aside>
      </div>

      <SiteFooter />
    </div>
  );
}
