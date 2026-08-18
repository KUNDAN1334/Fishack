/**
 * Next.js config — the API proxy is the whole point of this file (ADR-027).
 *
 * Every backend call goes to a relative `/api/...` path, and Next rewrites it
 * onto FastAPI. So the browser only ever talks to one origin.
 *
 * Why this rather than calling http://localhost:8000 directly with CORS on the
 * backend:
 *
 *   1. No CORS at all. Same-origin requests skip preflight entirely — and
 *      CORS combined with a streaming response is genuinely nasty to debug,
 *      because a misconfigured header produces a stream that just stops with
 *      no useful error.
 *   2. One config for two environments. In Docker the backend is `api:8000`
 *      on the compose network; locally it is `localhost:8000`. Only this env
 *      var changes — no frontend code is aware of either.
 *   3. It is what a real deployment looks like anyway: a reverse proxy in
 *      front of both, serving one hostname.
 *
 * `API_ORIGIN` is read at build/start time on the SERVER, so it is never
 * shipped to the browser — the browser has no idea the backend exists.
 */
const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output copies only the files the server actually needs, which
  // keeps the Docker image around 150MB instead of shipping node_modules.
  output: "standalone",
  async rewrites() {
    // Generic proxy for the chat and feedback endpoints. /api/admin/stats is
    // handled by a route handler instead (app/api/admin/stats/route.ts),
    // because the admin token must be attached to the OUTGOING request and a
    // rewrite cannot do that. Route handlers shadow afterFiles rewrites, so
    // that path wins without any special-casing here.
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
