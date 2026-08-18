/**
 * Server-side proxy for GET /admin/stats.
 *
 * This exists rather than a plain rewrite because the admin token has to be
 * attached to the OUTGOING request, and `headers()` in `next.config.mjs` sets
 * *response* headers — it cannot add a header to a proxied request. A route
 * handler runs on the server, so it can read the secret and forward it.
 *
 * It also means the token never reaches the browser. A `NEXT_PUBLIC_` variable
 * would be inlined into the client bundle, which for a secret is the same as
 * publishing it.
 *
 * Route handlers take precedence over `afterFiles` rewrites, so this shadows
 * the generic `/api/:path*` rule for exactly this path and nothing else.
 */

import { NextRequest } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "";

export async function GET(request: NextRequest) {
  const search = request.nextUrl.search;

  try {
    const upstream = await fetch(`${API_ORIGIN}/admin/stats${search}`, {
      headers: ADMIN_TOKEN ? { "X-Admin-Token": ADMIN_TOKEN } : {},
      // Always fresh. A cached operations dashboard is worse than a slow one —
      // it would show a healthy system after it stopped being healthy.
      cache: "no-store",
    });

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    // The backend being unreachable is the common case in a fresh deployment,
    // so say which side failed rather than returning a bare 500.
    //
    // `new Response(JSON.stringify(...))` rather than `Response.json(...)`:
    // the static helper is newer and its presence depends on the TS lib
    // version, and this file is not covered by any test.
    const detail =
      `Could not reach the API at ${API_ORIGIN}. ` +
      (err instanceof Error ? err.message : "unknown error");
    return new Response(JSON.stringify({ detail }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
