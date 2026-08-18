import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fishack — grounded support answers",
  description:
    "Fishack fishes out the exact answer from a sea of docs — every claim cited, verified and confidence-gated.",
};

/**
 * App shell.
 *
 * The tagline is in the header rather than buried in an about page because it
 * is a PROMISE the UI has to keep visibly: cited, verified, confidence-gated,
 * escalates instead of hallucinating. Every element below — the sources panel,
 * the confidence pill, the escalation banner — exists to make one clause of it
 * observable.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full flex flex-col">
        <header className="shrink-0 border-b border-slate-200 bg-white">
          <div className="mx-auto max-w-[1400px] px-5 py-3 flex items-center gap-4">
            <Link href="/" className="flex items-baseline gap-2 group">
              <span className="text-xl">🎣</span>
              <span className="text-lg font-semibold text-slate-900 group-hover:text-ocean-600">
                Fishack
              </span>
            </Link>
            <p className="hidden lg:block text-xs text-slate-500 border-l border-slate-200 pl-4">
              Every claim cited, verified and confidence-gated — when it isn&apos;t sure,
              it escalates instead of guessing.
            </p>
            <nav className="ml-auto flex items-center gap-1 text-sm">
              <Link
                href="/"
                className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                Chat
              </Link>
              <Link
                href="/admin"
                className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                Admin
              </Link>
            </nav>
          </div>
        </header>

        {/* min-h-0 is load-bearing: without it a flex child refuses to shrink
            below its content, and the inner scroll areas grow the page
            instead of scrolling. */}
        <main className="flex-1 min-h-0">{children}</main>
      </body>
    </html>
  );
}
