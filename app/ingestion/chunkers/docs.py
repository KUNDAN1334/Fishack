"""Structure-aware chunker for product docs (Design.md §4, row 1).

The idea: a docs page ALREADY has a semantic structure — its headings. A
fixed-size splitter ignores that and cuts mid-explanation; respecting it
gives chunks that are self-contained by construction.

Algorithm:
  1. Parse the markdown into a flat list of blocks, each tagged with the
     heading path it lives under ("Webhooks > Retry Logic").
  2. Group blocks into sections by heading path.
  3. Per section:
       - fits in MAX_CHUNK_TOKENS  -> one chunk
       - too big                   -> split on paragraph boundaries with
                                      OVERLAP_TOKENS of carry-over
       - too small                 -> merge into the previous chunk if they
                                      share a parent heading
  4. Prepend the heading path to every chunk's content (ADR-004), so both
     the tsvector and the embedding see the section's topic words even when
     the body never repeats them.

Tables are never split: a half-table is unusable to both a reader and a
model, and its markdown becomes malformed. A table larger than the budget
gets its own oversized chunk (hard-capped at MAX_MODEL_TOKENS).
"""

from __future__ import annotations

import re

from app.ingestion.chunkers.base import (
    MAX_CHUNK_TOKENS,
    MAX_MODEL_TOKENS,
    MIN_CHUNK_TOKENS,
    OVERLAP_TOKENS,
    TARGET_CHUNK_TOKENS,
    Chunker,
    register,
)
from app.ingestion.models import ParsedDocument, ProtoChunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)

HEADING_SEPARATOR = " > "


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def parse_sections(markdown: str) -> list[tuple[str, str]]:
    """Markdown -> [(heading_path, section_text), ...] in document order.

    The heading path accumulates ancestors: an H3 under an H2 under the H1
    title becomes "Webhooks Overview > Retry Logic > Backoff Schedule".
    Content before any heading is attributed to the empty path (rare —
    usually a lead paragraph).
    """
    lines = strip_frontmatter(markdown).split("\n")
    sections: list[tuple[str, str]] = []
    # stack[i] holds the heading text at level i+1
    stack: list[str] = []
    current_path = ""
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append((current_path, text))
        buffer.clear()

    for line in lines:
        match = HEADING_RE.match(line)
        if not match:
            buffer.append(line)
            continue
        flush()
        level = len(match.group(1))
        heading = match.group(2).strip()
        # Truncate the stack to this level, then push. Handles skipped
        # levels (H1 -> H3) without crashing.
        del stack[level - 1:]
        while len(stack) < level - 1:
            stack.append("")  # placeholder for a skipped level
        stack.append(heading)
        current_path = HEADING_SEPARATOR.join(h for h in stack if h)

    flush()
    return sections


def split_blocks(text: str) -> list[str]:
    """Split a section into atomic blocks: paragraphs, whole tables, whole
    code fences. These are the smallest units we will never cut through."""
    blocks: list[str] = []
    buffer: list[str] = []
    in_table = False
    in_fence = False

    def flush() -> None:
        joined = "\n".join(buffer).strip()
        if joined:
            blocks.append(joined)
        buffer.clear()

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("```"):
            # Code fences are atomic: a half-fence breaks rendering AND
            # confuses the model about where code ends.
            if in_fence:
                buffer.append(line)
                flush()
                in_fence = False
            else:
                flush()
                buffer.append(line)
                in_fence = True
            continue
        if in_fence:
            buffer.append(line)
            continue

        is_table_line = stripped.startswith("|")
        if is_table_line and not in_table:
            flush()          # table starts: close whatever came before
            in_table = True
        elif in_table and not is_table_line:
            flush()          # table ends: emit it as one atomic block
            in_table = False

        if not stripped and not in_table:
            flush()          # blank line = paragraph boundary
            continue
        buffer.append(line)

    flush()
    return blocks


@register
class DocsChunker(Chunker):
    source_type = "docs"

    def chunk(self, document: ParsedDocument) -> list[ProtoChunk]:
        chunks: list[ProtoChunk] = []
        for heading_path, section_text in parse_sections(document.content):
            for content, tokens in self._chunk_section(heading_path, section_text):
                chunks.append(
                    ProtoChunk(
                        chunk_index=0,  # assigned after merging, below
                        content=content,
                        token_count=tokens,
                        heading_path=heading_path or None,
                        metadata={
                            "doc_version": document.doc_version,
                            "product_area": document.product_area,
                            "source_type": "docs",
                        },
                    )
                )
        chunks = self._merge_small_chunks(chunks)
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        return chunks

    # ------------------------------------------------------------ internals --

    def _prefix(self, heading_path: str) -> str:
        """ADR-004: the heading path becomes part of the embedded text."""
        return f"{heading_path}\n\n" if heading_path else ""

    def _chunk_section(self, heading_path: str, text: str) -> list[tuple[str, int]]:
        """One section -> one or more (content, token_count) pairs."""
        prefix = self._prefix(heading_path)
        prefix_tokens = self.tokens.count(prefix) if prefix else 0
        whole = prefix + text

        if self.tokens.count(whole) <= MAX_CHUNK_TOKENS:
            return [(whole, self.tokens.count(whole))]

        # Section is too big: pack blocks up to TARGET, then carry overlap.
        blocks = split_blocks(text)
        results: list[tuple[str, int]] = []
        current: list[str] = []
        current_tokens = prefix_tokens

        for block in blocks:
            block_tokens = self.tokens.count(block)

            # A single block bigger than the model limit must be hard-split;
            # nothing structural can save us here.
            if block_tokens > MAX_MODEL_TOKENS:
                if current:
                    results.append((prefix + "\n\n".join(current), current_tokens))
                    current, current_tokens = [], prefix_tokens
                for piece in self._hard_split(block, prefix_tokens):
                    results.append((prefix + piece, self.tokens.count(prefix + piece)))
                continue

            if current and current_tokens + block_tokens > TARGET_CHUNK_TOKENS:
                results.append((prefix + "\n\n".join(current), current_tokens))
                # Overlap: carry the tail of the emitted chunk into the next
                # one so a fact spanning the boundary survives intact.
                carry = self._overlap_tail(current)
                current = list(carry)
                current_tokens = prefix_tokens + sum(self.tokens.count(c) for c in carry)

            current.append(block)
            current_tokens += block_tokens

        if current:
            results.append((prefix + "\n\n".join(current), current_tokens))
        return self._enforce_model_limit(results)

    def _overlap_tail(self, blocks: list[str]) -> list[str]:
        """Take trailing blocks worth roughly OVERLAP_TOKENS.

        Whole blocks only — overlapping half a paragraph would reintroduce
        exactly the mid-sentence cut we're avoiding. Tables are excluded:
        duplicating a table into the next chunk wastes a lot of budget for
        little recall gain.
        """
        tail: list[str] = []
        total = 0
        for block in reversed(blocks):
            if block.lstrip().startswith("|"):
                break
            block_tokens = self.tokens.count(block)
            if total + block_tokens > OVERLAP_TOKENS and tail:
                break
            tail.insert(0, block)
            total += block_tokens
            if total >= OVERLAP_TOKENS:
                break
        return tail

    def _hard_split(self, block: str, prefix_tokens: int) -> list[str]:
        """Last resort for a single oversized block (a giant table or a wall
        of text with no paragraph breaks): split on sentence boundaries, then
        on whitespace if even that fails.

        Measures the ACTUAL joined candidate rather than summing per-unit
        counts. Token counts are not additive — joining adds separator
        characters, and a real BPE tokenizer merges differently across a
        boundary than it does in isolation. Summing parts underestimates, and
        underestimating here means silent truncation at the model.
        """
        budget = max(1, MAX_MODEL_TOKENS - prefix_tokens)
        units = re.split(r"(?<=[.!?])\s+", block)
        if len(units) == 1:
            units = block.split("\n") if "\n" in block else block.split(" ")

        pieces: list[str] = []
        current: list[str] = []
        for unit in units:
            candidate = current + [unit]
            if current and self.tokens.count(" ".join(candidate)) > budget:
                pieces.append(" ".join(current))
                current = [unit]
            else:
                current = candidate
        if current:
            pieces.append(" ".join(current))
        return pieces

    def _enforce_model_limit(self, results: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Final safety net: nothing leaves the chunker above MAX_MODEL_TOKENS.

        The packing loop tracks a RUNNING SUM of per-block counts, which can
        drift below the true count of the joined text (see _hard_split). This
        pass re-measures every finished chunk and splits any that drifted
        over. Cheap insurance against the worst ingestion bug there is:
        embeddings silently computed on truncated text, where everything
        still "works" and retrieval is quietly degraded.
        """
        safe: list[tuple[str, int]] = []
        for content, _claimed in results:
            actual = self.tokens.count(content)
            if actual <= MAX_MODEL_TOKENS:
                safe.append((content, actual))
                continue
            for piece in self._hard_split(content, prefix_tokens=0):
                safe.append((piece, self.tokens.count(piece)))
        return safe

    def _merge_small_chunks(self, chunks: list[ProtoChunk]) -> list[ProtoChunk]:
        """Fold undersized chunks into the previous one when they share a
        parent heading.

        Why: a stub section ("### Dead Letter Queue" with two sentences) is a
        poor retrieval unit on its own — it has no context. Merging it with
        its sibling keeps it findable. We only merge under a shared parent so
        unrelated topics never end up in one chunk.
        """
        if not chunks:
            return chunks
        merged: list[ProtoChunk] = [chunks[0]]
        for chunk in chunks[1:]:
            previous = merged[-1]
            combined_tokens = previous.token_count + chunk.token_count
            if (
                chunk.token_count < MIN_CHUNK_TOKENS
                and combined_tokens <= MAX_CHUNK_TOKENS
                and _shares_parent(previous.heading_path, chunk.heading_path)
            ):
                previous.content = f"{previous.content}\n\n{chunk.content}"
                previous.token_count = combined_tokens
                continue
            merged.append(chunk)
        return merged


def _shares_parent(path_a: str | None, path_b: str | None) -> bool:
    """True if two heading paths share their first component (same H1/H2
    branch), or one is an ancestor of the other."""
    if not path_a or not path_b:
        return False
    parts_a = path_a.split(HEADING_SEPARATOR)
    parts_b = path_b.split(HEADING_SEPARATOR)
    if path_b.startswith(path_a) or path_a.startswith(path_b):
        return True
    return parts_a[:-1] == parts_b[:-1] and len(parts_a) > 1
