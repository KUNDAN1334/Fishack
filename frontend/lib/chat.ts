/**
 * The SSE client — hand-parsed, because `EventSource` cannot POST.
 *
 * This is the one genuinely non-obvious piece of frontend code in the project,
 * so it is worth being explicit about why it exists.
 *
 * The browser has a built-in SSE client, `EventSource`. It is GET-only. Our
 * chat request carries a tenant, a query and the conversation history — far
 * too much for a query string, and putting a user's conversation in a URL is
 * a bad idea regardless (it lands in logs, in history, in referrers).
 *
 * So: `fetch` with a POST body, then read `response.body` as a stream and
 * parse the SSE framing by hand. It is about thirty lines, and it mirrors
 * exactly what the backend does with the LLM providers' SSE in
 * `app/llm/providers/openai_compat.py` — same format, same reason, opposite
 * direction.
 *
 * THE BUFFERING RULE. A network chunk is not an SSE event. One `read()` can
 * deliver half an event, three events, or an event split mid-JSON. So we
 * accumulate into a buffer and only parse up to the last complete `\n\n`
 * separator, keeping the remainder for the next read. Parsing each chunk
 * independently works perfectly in development — where responses are small
 * and arrive whole — and corrupts randomly in production under real network
 * conditions. That is the classic streaming bug.
 */

import type { ChatMeta, ChatResponse, Turn } from "./types";

export interface StreamHandlers {
  onMeta: (meta: ChatMeta) => void;
  onDelta: (text: string) => void;
  onFinal: (response: ChatResponse) => void;
  onError: (message: string) => void;
}

interface ParsedEvent {
  event: string;
  data: string;
}

/**
 * Split a completed SSE block into its event name and data payload.
 *
 * The backend emits `event: <type>` then `data: <json>`. Per the SSE spec a
 * data field can span multiple lines, so they are joined rather than
 * overwritten — currently the backend never does that, but a parser that
 * quietly drops data the moment the producer changes is a trap.
 */
function parseBlock(block: string): ParsedEvent | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    // Anything else (comments, `id:`, `retry:`) is ignored by design.
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export async function streamChat(
  body: {
    tenant_id: string;
    query: string;
    messages: { role: string; content: string }[];
    conversation_id: string | null;
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    // Relative path — Next rewrites it onto FastAPI (ADR-027), so this is
    // same-origin and there is no CORS involved.
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    handlers.onError(
      err instanceof Error && err.name === "AbortError"
        ? "cancelled"
        : "Could not reach the server. Is the API running?",
    );
    return;
  }

  if (!response.ok) {
    // Errors BEFORE the stream starts are ordinary HTTP, with a JSON body —
    // 404 for an unknown tenant, 422 for an empty query. Once the stream has
    // begun the status is already sent, and the backend switches to an
    // `error` SSE event instead. Two paths, because HTTP gives us no choice.
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = String(payload.detail);
    } catch {
      /* non-JSON error body — keep the status message */
    }
    handlers.onError(detail);
    return;
  }

  if (!response.body) {
    handlers.onError("The server returned no stream.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      // `stream: true` matters: a multi-byte UTF-8 character can be split
      // across two network chunks, and decoding each independently would
      // produce a replacement character mid-word.
      buffer += decoder.decode(value, { stream: true });

      // Parse only up to the last complete event; keep the remainder.
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const parsed = parseBlock(block);
        if (!parsed) continue;

        try {
          const payload = JSON.parse(parsed.data);
          if (parsed.event === "meta") handlers.onMeta(payload.data ?? {});
          else if (parsed.event === "delta") handlers.onDelta(payload.text ?? "");
          else if (parsed.event === "final") handlers.onFinal(payload.data as ChatResponse);
          else if (parsed.event === "error") handlers.onError(payload.text ?? "stream error");
        } catch {
          // One malformed event must not kill a stream that is otherwise
          // delivering a good answer.
          console.warn("skipping unparseable SSE event", parsed);
        }
      }
    }
  } catch (err) {
    if (!(err instanceof Error && err.name === "AbortError")) {
      handlers.onError("The connection dropped while the answer was streaming.");
    }
  } finally {
    reader.releaseLock();
  }
}

/** POST /feedback. Fire-and-forget: a failed rating must not disturb the chat. */
export async function sendFeedback(
  traceId: string,
  rating: 1 | -1,
  comment?: string,
): Promise<boolean> {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trace_id: traceId, rating, comment: comment ?? null }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Conversation history for the backend: text only, never the sources.
 *
 * The prompt builder follows the same rule (Phase 3). Re-injecting earlier
 * turns' chunks would let the model answer turn 3 from turn 1's context — and
 * its citation markers would then point at sources absent from the current
 * numbering, which post-hoc validation would flag as fabricated.
 */
export function toHistory(turns: Turn[]): { role: string; content: string }[] {
  return turns
    .filter((turn) => !turn.pending && !turn.error && turn.content.trim())
    .map((turn) => ({ role: turn.role, content: turn.content }));
}
