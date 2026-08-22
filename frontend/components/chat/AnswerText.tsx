"use client";

/**
 * Renders answer text with clickable [n] citation markers.
 *
 * The parsing rules match `app/generation/citations.py` deliberately — the
 * backend's validator and this renderer must agree on what a citation IS, or
 * the UI will offer a marker the validator never checked, or fail to show one
 * it did.
 *
 * So: only digits inside brackets, and not preceded by a word character. That
 * second rule is what stops `items[0]` in a code sample becoming a fake
 * citation link, while `[1][3]` still works because `]` is not a word
 * character. Same regex, same reason, on both sides of the wire.
 *
 * Redesign note: markers are `<button>` elements with an `aria-label` naming
 * the source. They were `<span>`s with click handlers, which meant the evidence
 * behind an answer — the product's entire claim — was unreachable by keyboard.
 */

import { useMemo } from "react";

// Mirrors CITATION_MARKER in app/generation/citations.py.
const MARKER = /(?<!\w)\[(\d+(?:\s*,\s*\d+)*)\]/g;

interface Props {
  text: string;
  /** Which indices actually exist. A marker outside this set is fabrication. */
  validIndices: Set<number>;
  activeIndex: number | null;
  onCitationClick: (index: number) => void;
  streaming?: boolean;
}

type Piece =
  | { kind: "text"; value: string }
  | { kind: "cite"; value: string; indices: number[] };

function split(text: string): Piece[] {
  const pieces: Piece[] = [];
  let cursor = 0;

  // `matchAll` needs the global flag and a fresh lastIndex; building the regex
  // per call would be wasteful, so reset it instead.
  MARKER.lastIndex = 0;
  for (const match of text.matchAll(MARKER)) {
    const at = match.index ?? 0;
    if (at > cursor) pieces.push({ kind: "text", value: text.slice(cursor, at) });
    pieces.push({
      kind: "cite",
      value: match[0],
      indices: match[1].split(",").map((part) => parseInt(part.trim(), 10)),
    });
    cursor = at + match[0].length;
  }
  if (cursor < text.length) pieces.push({ kind: "text", value: text.slice(cursor) });
  return pieces;
}

export default function AnswerText({
  text,
  validIndices,
  activeIndex,
  onCitationClick,
  streaming,
}: Props) {
  const pieces = useMemo(() => split(text), [text]);

  return (
    <div className={`whitespace-pre-wrap leading-[1.7] ${streaming ? "caret" : ""}`}>
      {pieces.map((piece, i) => {
        if (piece.kind === "text") return <span key={i}>{piece.value}</span>;

        // A marker pointing at a source that was never offered. Shown in rose
        // rather than hidden: Design.md §7 asks us to FLAG fabricated
        // citations, not suppress them — the answer may still be correct, and
        // quietly swallowing the evidence would be its own failure.
        //
        // Rendered as a `<span>` on purpose. It is not a link to anywhere,
        // because there is nowhere to go; making it look clickable would
        // promise a source that does not exist.
        const fabricated = piece.indices.some((n) => !validIndices.has(n));
        if (fabricated) {
          return (
            <span
              key={i}
              className="mx-0.5 inline-flex items-baseline rounded-sm border border-rose-300
                         bg-rose-50 px-1 align-super font-mono text-[10px] font-semibold text-rose-700"
            >
              {piece.value}
              <span className="sr-only">
                {" "}
                — fabricated citation: this points at a source that was never provided to the model
              </span>
            </span>
          );
        }

        const active = piece.indices.some((n) => n === activeIndex);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCitationClick(piece.indices[0])}
            aria-label={`Show source ${piece.indices.join(" and ")}`}
            className={`mx-0.5 inline-flex items-baseline rounded-sm px-1 align-super font-mono
                        text-[10px] font-semibold transition-colors ${
                          active
                            ? "bg-ocean-600 text-white"
                            : "bg-ocean-100 text-ocean-800 hover:bg-ocean-200"
                        }`}
          >
            {piece.value}
          </button>
        );
      })}
    </div>
  );
}
