"use client";

/**
 * A code block with a language chip and a copy button.
 *
 * No syntax highlighter. Shiki or Prism would add 40-200 KB to a documentation
 * bundle to colour shell commands and a handful of SQL snippets, and the
 * highlighted result is not measurably easier to act on than mono text with a
 * language label. If a page ever needs a hundred lines of annotated source,
 * that is the moment to reconsider — not before.
 *
 * The copy button uses the async clipboard API, which is available only in a
 * secure context. On plain HTTP it will reject, so the failure is caught and
 * the button simply does not confirm rather than throwing into the console.
 */

import { useState } from "react";
import { Check, Copy } from "@/components/ui/Icon";

export default function CodeBlock({
  code,
  language = "shell",
  /** Shown above the block when the snippet belongs to a specific file. */
  filename,
}: {
  code: string;
  language?: string;
  filename?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Insecure context or a denied permission. Nothing useful to say — the
      // text is selectable, which is the fallback everyone already knows.
    }
  }

  return (
    <div className="!mt-5 overflow-hidden rounded-lg border border-line bg-surface-sunken">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <span className="font-mono text-2xs uppercase tracking-[0.1em] text-slate-400">
          {filename ?? language}
        </span>
        <button
          type="button"
          onClick={copy}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-2xs
                     font-medium text-slate-500 transition-colors hover:bg-slate-200/60 hover:text-slate-800"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="thin-scroll overflow-x-auto px-4 py-3.5 text-xs leading-[1.7] text-slate-700">
        <code>{code}</code>
      </pre>
    </div>
  );
}
