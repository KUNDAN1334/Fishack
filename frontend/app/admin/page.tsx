"use client";

/**
 * Admin dashboard — renders GET /admin/stats (Design.md §12).
 *
 * Everything here is computed by the backend from the `traces` table, which
 * has carried one row per request since Phase 3. The frontend does no maths
 * beyond formatting, deliberately: if the dashboard derived its own rates,
 * they could disagree with what the eval harness and the triage script read
 * from the same rows. One source of truth, three consumers.
 *
 * Auth: the request goes through app/api/admin/stats/route.ts, a server-side
 * proxy that attaches ADMIN_TOKEN. The token is never in the browser bundle.
 * With ADMIN_TOKEN unset the endpoint is open, which is right locally and a
 * data leak in public — this is the one view that reads ACROSS tenants.
 *
 * PRODUCTION NOTE: a shared token is the floor. Real deployments put this
 * behind SSO with an admin role and audit every access.
 */

import { useCallback, useEffect, useState } from "react";
import type { Stats } from "@/lib/types";

const WINDOWS = [
  { hours: 1, label: "1h" },
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}

/** One headline number. `tone` is used only where a value has a good direction. */
function Metric({
  label, value, sub, tone = "neutral", hint,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
  hint?: string;
}) {
  const colour = {
    neutral: "text-slate-900",
    good: "text-emerald-600",
    warn: "text-amber-600",
    bad: "text-rose-600",
  }[tone];

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4"
      title={hint}
    >
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${colour}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/stats?hours=${hours}`);
      if (res.status === 401) {
        throw new Error(
          "401 — this deployment has ADMIN_TOKEN set on the API but not on the " +
            "frontend. Add the same value as ADMIN_TOKEN in the frontend's " +
            "environment and redeploy.",
        );
      }
      if (!res.ok) throw new Error(`stats returned ${res.status}`);
      setStats(await res.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load stats");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    load();
    // 15s refresh. Fast enough to watch numbers move while demoing, slow
    // enough that the trace-table scan is not a self-inflicted load test.
    const timer = setInterval(load, 15_000);
    return () => clearInterval(timer);
  }, [load]);

  if (loading) {
    return <div className="p-8 text-sm text-slate-500">Loading metrics…</div>;
  }

  if (error || !stats) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <p className="font-medium">Could not load /admin/stats</p>
          <p className="mt-1 text-rose-700">{error}</p>
          <p className="mt-2 text-[12px] text-rose-600">
            Is the API running? <code>make api</code>, or{" "}
            <code>docker compose up -d</code>.
          </p>
        </div>
      </div>
    );
  }

  const { requests, latency_ms, cost, quality, escalations, by_tenant, providers } = stats;
  const noTraffic = requests.total === 0;

  return (
    <div className="h-full overflow-y-auto thin-scroll">
      <div className="mx-auto max-w-6xl px-5 py-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Operations</h1>
            <p className="text-xs text-slate-500">
              From the traces table — one row per request since Phase 3. Auto-refreshes
              every 15s.
            </p>
          </div>
          <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
            {WINDOWS.map((w) => (
              <button
                key={w.hours}
                onClick={() => setHours(w.hours)}
                className={`rounded px-2.5 py-1 text-xs ${
                  hours === w.hours
                    ? "bg-ocean-600 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
        </div>

        {noTraffic && (
          <div className="mb-5 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
            No requests in this window. Ask something on the{" "}
            <a href="/" className="text-ocean-600 underline">chat page</a> and the numbers
            will appear.
          </div>
        )}

        {/* ---- headline ------------------------------------------------- */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Requests" value={String(requests.total)} sub={`last ${hours}h`} />
          <Metric
            label="Escalation rate"
            value={pct(requests.escalation_rate)}
            sub="declined to answer"
            // Cuts both ways (Design.md §12): too high means retrieval is
            // failing, too low means the confidence gate is protecting nobody.
            tone={
              requests.escalation_rate > 0.4 ? "bad"
              : requests.escalation_rate > 0.2 ? "warn"
              : "good"
            }
            hint="Too high means retrieval is failing. Too low means the confidence gate isn't protecting anyone."
          />
          <Metric
            label="Cache hit rate"
            value={pct(requests.cache_hit_rate)}
            sub="LLM calls skipped"
            tone={requests.cache_hit_rate > 0.2 ? "good" : "neutral"}
          />
          <Metric
            label="Cost / query"
            value={`$${cost.per_query_usd.toFixed(6)}`}
            sub="virtual — see methodology"
            tone={cost.per_query_usd < 0.02 ? "good" : "warn"}
            hint={cost.methodology}
          />
        </div>

        {/* ---- latency --------------------------------------------------- */}
        <h2 className="mt-6 mb-2 text-sm font-semibold text-slate-800">Latency</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="p50" value={ms(latency_ms.p50)} />
          <Metric
            label="p95"
            value={ms(latency_ms.p95)}
            sub="SLA target < 3s"
            tone={latency_ms.p95 > 3000 ? "bad" : "good"}
          />
          <Metric label="retrieval (mean)" value={ms(latency_ms.mean_retrieval)} />
          <Metric
            label="rerank (mean)"
            value={ms(latency_ms.mean_rerank)}
            // Almost always the dominant stage on CPU — which is why the
            // breakdown is here rather than just a total.
            tone={latency_ms.mean_rerank > 1500 ? "warn" : "neutral"}
            hint="The cross-encoder on CPU. Usually the stage that owns p95."
          />
          <Metric label="generation (mean)" value={ms(latency_ms.mean_generation)} />
        </div>

        {/* ---- quality --------------------------------------------------- */}
        <h2 className="mt-6 mb-2 text-sm font-semibold text-slate-800">Answer quality</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Satisfaction"
            value={
              quality.thumbs_up + quality.thumbs_down > 0
                ? pct(quality.satisfaction_rate)
                : "—"
            }
            sub={`👍 ${quality.thumbs_up}  👎 ${quality.thumbs_down}`}
            tone={quality.satisfaction_rate >= 0.8 ? "good" : "neutral"}
          />
          <Metric
            label="Fabricated citations"
            value={String(quality.answers_with_fabricated_citations)}
            sub="answers citing a source that wasn't offered"
            tone={quality.answers_with_fabricated_citations > 0 ? "bad" : "good"}
          />
          <Metric
            label="Mean confidence"
            value={quality.mean_confidence.toFixed(3)}
            sub="mixed scales — see per-answer detail"
            hint="Averaged across reranker (0-1) and fusion (~0.02) scores, so read it as a trend not an absolute."
          />
          <Metric
            label="Open escalations"
            value={String(escalations.open)}
            sub={Object.entries(escalations.by_reason)
              .map(([reason, n]) => `${reason}: ${n}`)
              .join("  ") || "none"}
            tone={escalations.open > 0 ? "warn" : "good"}
          />
        </div>

        {/* ---- per tenant ------------------------------------------------ */}
        {by_tenant.length > 0 && (
          <>
            <h2 className="mt-6 mb-2 text-sm font-semibold text-slate-800">By tenant</h2>
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Tenant</th>
                    <th className="px-4 py-2 text-right font-medium">Requests</th>
                    <th className="px-4 py-2 text-right font-medium">Escalation</th>
                    <th className="px-4 py-2 text-right font-medium">Cache hits</th>
                    <th className="px-4 py-2 text-right font-medium">p95</th>
                    <th className="px-4 py-2 text-right font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {by_tenant.map((row) => (
                    <tr key={row.tenant_id}>
                      <td className="px-4 py-2 font-medium text-slate-800">{row.tenant_id}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{row.requests}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {pct(row.escalation_rate)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {pct(row.cache_hit_rate)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{ms(row.p95_ms)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        ${row.cost_usd.toFixed(5)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* ---- provider quota -------------------------------------------- */}
        <h2 className="mt-6 mb-2 text-sm font-semibold text-slate-800">
          Provider usage today
        </h2>
        <p className="mb-2 text-xs text-slate-500">
          Daily counters from Redis. Free tiers are the constraint this project is
          engineered around — the fallback chain exists so one exhausted provider
          doesn&apos;t stop the system.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.keys(providers).length === 0 || typeof providers.error === "string" ? (
            <div className="col-span-full rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
              {typeof providers.error === "string"
                ? `Quota unavailable: ${providers.error}`
                : "No provider usage recorded yet."}
            </div>
          ) : (
            Object.entries(providers).map(([name, usage]) => {
              if (typeof usage === "string") return null;
              return (
                <div key={name} className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-[11px] uppercase tracking-wide text-slate-400">{name}</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
                    {usage.requests ?? 0}
                    <span className="ml-1 text-xs font-normal text-slate-400">requests</span>
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-400 tabular-nums">
                    {(usage.tokens_in ?? 0) + (usage.tokens_out ?? 0)} tokens · $
                    {(usage.virtual_cost_usd ?? 0).toFixed(5)}
                  </p>
                </div>
              );
            })
          )}
        </div>

        <p className="mt-6 text-[11px] text-slate-400">
          {cost.methodology}. Total this window: ${cost.total_usd.toFixed(5)} across{" "}
          {cost.tokens_in.toLocaleString()} in / {cost.tokens_out.toLocaleString()} out.
        </p>
      </div>
    </div>
  );
}
