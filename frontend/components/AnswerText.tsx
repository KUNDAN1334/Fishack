"use client";

/**
 * Renders answer text with clickable [n] citation markers.
 *
 * The parsing rules match `app/generation/citations.py` deliberately — the
 * backend's validator and this renderer must agree on what a citation IS, or
 * the UI will offer a marker the validator never checked (or fail to show one
 * it did).
 *
 * So: only digits inside brackets, and not preceded by a word character. That
 * second rule is what stops `items[0]` in a code sample becoming a fake
 * citation link, while `[1][3]` still works because `]` is not a word
 * character. Same regex, same reason, on both sides of the wire.
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

  // `matchAll` needs the global flag and a fresh lastIndex; building the
  // regex per call would be wasteful, so reset it instead.
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
    <div className={`whitespace-pre-wrap leading-relaxed ${streaming ? "caret" : ""}`}>
      {pieces.map((piece, i) => {
        if (piece.kind === "text") return <span key={i}>{piece.value}</span>;

        // A marker pointing at a source that was never offered. Shown in red
        // rather than hidden: Design.md §7 asks us to FLAG fake citations,
        // not to suppress them — the answer may still be correct, and quietly
        // swallowing the evidence would be its own failure.
        const fabricated = piece.indices.some((n) => !validIndices.has(n));
        if (fabricated) {
          return (
            <span
              key={i}
              title="This citation points at a source that was never provided to the model."
              className="mx-0.5 rounded px-1 text-xs font-semibold align-super
                         bg-rose-100 text-rose-700 ring-1 ring-rose-300 cursor-help"
            >
              {piece.value}
            </span>
          );
        }

        const active = piece.indices.some((n) => n === activeIndex);
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCitationClick(piece.indices[0])}
            title="Show this source"
            className={`mx-0.5 rounded px-1 text-xs font-semibold align-super transition-colors
                        ${
                          active
                            ? "bg-ocean-500 text-white"
                            : "bg-ocean-100 text-ocean-700 hover:bg-ocean-300 hover:text-ocean-900"
                        }`}
          >
            {piece.value}
          </button>
        );
      })}
    </div>
  );
}
