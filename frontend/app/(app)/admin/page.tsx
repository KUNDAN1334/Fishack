"use client";

/**
 * Operations dashboard — renders GET /admin/stats.
 *
 * Everything here is computed by the backend from the `traces` table, which has
 * carried one row per request since Phase 3. The frontend does no arithmetic
 * beyond formatting, deliberately: if the dashboard derived its own rates they
 * could disagree with what the eval harness and the triage script read from the
 * same rows. One source of truth, three consumers.
 *
 * The redesign regrouped the page around the four questions an operator
 * actually arrives with — is it working, is it fast, is it trustworthy, is it
 * leaking — rather than around the metric families the API happens to return.
 *
 * Auth: the request goes through `app/api/admin/stats/route.ts`, a server-side
 * proxy that attaches ADMIN_TOKEN. The token never reaches the browser bundle.
 * With ADMIN_TOKEN unset the endpoint is open, which is right locally and a
 * data leak in public — this is the one view that reads ACROSS tenants.
 *
 * PRODUCTION NOTE: a shared token is the floor. A real deployment puts this
 * behind SSO with an admin role and audits every access.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import MetricCard, { ms, pct } from "@/components/admin/MetricCard";
import Section from "@/components/admin/Section";
import StageBars from "@/components/admin/StageBars";
import { AlertTriangle, Lock, RefreshCw } from "@/components/ui/Icon";
import type { Stats } from "@/lib/types";

const WINDOWS = [
  { hours: 1, label: "1h" },
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

/** Distinguishes "the token is wrong" from "the API is down". They need different fixes. */
type LoadError = { kind: "unauthorised" | "unreachable" | "other"; detail: string };

function Skeleton() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-6">
      <div className="h-6 w-40 animate-pulse rounded bg-slate-200" />
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-[92px] animate-pulse rounded-lg bg-slate-200/70" />
        ))}
      </div>
    </div>
  );
}

export default function OperationsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<LoadError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/admin/stats?hours=${hours}`);
      if (response.status === 401) {
        setError({
          kind: "unauthorised",
          detail:
            "The stats endpoint returned 401. The token is attached server-side by the route " +
            "handler, so this is an environment problem rather than a session one.",
        });
        return;
      }
      if (response.status === 502) {
        setError({ kind: "unreachable", detail: "The frontend could not reach the API." });
        return;
      }
      if (!response.ok) {
        setError({ kind: "other", detail: `stats returned ${response.status}` });
        return;
      }
      setStats(await response.json());
      setError(null);
    } catch (err) {
      setError({
        kind: "unreachable",
        detail: err instanceof Error ? err.message : "could not load stats",
      });
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    load();
    // 15s refresh. Fast enough to watch numbers move while demonstrating, slow
    // enough that the trace-table scan is not a self-inflicted load test.
    const timer = setInterval(load, 15_000);
    return () => clearInterval(timer);
  }, [load]);

  if (loading && !stats) return <Skeleton />;

  if (error && !stats) {
    const unauthorised = error.kind === "unauthorised";
    return (
      <div className="mx-auto max-w-3xl px-5 py-10">
        <div
          className={`rounded-xl border p-5 ${
            unauthorised ? "border-amber-200 bg-amber-50" : "border-rose-200 bg-rose-50"
          }`}
        >
          <p
            className={`flex items-center gap-2 text-sm font-semibold ${
              unauthorised ? "text-amber-900" : "text-rose-900"
            }`}
          >
            {unauthorised ? <Lock size={15} /> : <AlertTriangle size={15} />}
            {unauthorised ? "Admin token missing or wrong" : "Could not load /admin/stats"}
          </p>
          <p className={`mt-2 text-sm leading-relaxed ${unauthorised ? "text-amber-800" : "text-rose-800"}`}>
            {error.detail}
          </p>
          <p className={`mt-3 text-xs leading-relaxed ${unauthorised ? "text-amber-700" : "text-rose-700"}`}>
            {unauthorised ? (
              <>
                Set <code className="rounded-sm bg-amber-100 px-1">ADMIN_TOKEN</code> to the same
                value where the frontend runs as the API has, and reload. No request was logged
                against your quota.
              </>
            ) : (
              <>
                Is the API running? <code className="rounded-sm bg-rose-100 px-1">make api</code>,
                or <code className="rounded-sm bg-rose-100 px-1">docker compose up -d</code>.
              </>
            )}
          </p>
          <button
            type="button"
            onClick={load}
            className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-line bg-surface
                       px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw size={12} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const { requests, latency_ms, cost, quality, escalations, by_tenant, providers } = stats;
  const noTraffic = requests.total === 0;
  const meanTotal =
    latency_ms.mean_retrieval + latency_ms.mean_rerank + latency_ms.mean_generation;
  const rerankShare = meanTotal > 0 ? latency_ms.mean_rerank / meanTotal : 0;

  return (
    <div className="thin-scroll h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-5 py-6">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Operations</h1>
            <p className="mt-1 text-xs text-slate-500">
              One row per request, from the <code className="rounded-sm bg-surface-sunken px-1">traces</code>{" "}
              table. Window since{" "}
              <span className="figure">{new Date(stats.window.since).toLocaleString()}</span> ·{" "}
              {stats.window.tenant_id ? `tenant ${stats.window.tenant_id}` : "all tenants"} ·
              refreshes every 15s.
            </p>
          </div>
          <div
            role="group"
            aria-label="Time window"
            className="flex gap-0.5 rounded-lg border border-line bg-surface-sunken p-0.5"
          >
            {WINDOWS.map((window) => (
              <button
                key={window.hours}
                type="button"
                onClick={() => setHours(window.hours)}
                aria-pressed={hours === window.hours}
                className={`figure rounded-md px-2.5 py-1 text-xs transition-colors ${
                  hours === window.hours
                    ? "bg-surface font-medium text-slate-900 shadow-card"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {window.label}
              </button>
            ))}
          </div>
        </div>

        {noTraffic && (
          <div className="mb-6 rounded-lg border border-line bg-surface px-4 py-3.5 text-sm text-slate-500">
            No requests in this window. Ask something in the{" "}
            <Link href="/try" className="font-medium text-ocean-700 underline underline-offset-2">
              assistant
            </Link>{" "}
            and the numbers will appear.
          </div>
        )}

        {/* ------------------------------------------------ is it working -- */}
        <Section
          id="working"
          question="Is it working?"
          hint="Escalation rate cuts both ways. Too high means retrieval is failing; too low means the confidence gate is protecting nobody."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Requests" value={requests.total} note={`last ${hours}h`} />
            <MetricCard
              label="Escalation rate"
              value={pct(requests.escalation_rate)}
              note="declined to answer, and opened a ticket"
              tone={
                requests.escalation_rate > 0.4 ? "bad" : requests.escalation_rate > 0.2 ? "warn" : "good"
              }
            />
            <MetricCard
              label="Cache hit rate"
              value={pct(requests.cache_hit_rate)}
              note="LLM calls skipped entirely"
              tone={requests.cache_hit_rate > 0.2 ? "good" : "neutral"}
            />
            <MetricCard
              label="Cost / query"
              value={`$${cost.per_query_usd.toFixed(6)}`}
              note="virtual — see the methodology below"
              tone={cost.per_query_usd < 0.02 ? "good" : "warn"}
            />
          </div>

          {Object.keys(requests.by_action).length > 0 && (
            <div className="mt-3 overflow-hidden rounded-lg border border-line bg-surface">
              <p className="border-b border-line px-4 py-2 text-2xs font-semibold uppercase tracking-[0.1em] text-slate-400">
                Outcome of every request
              </p>
              <ul className="divide-y divide-line">
                {Object.entries(requests.by_action).map(([action, count]) => (
                  <li key={action} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <span className="w-32 text-slate-700">{action.replace(/_/g, " ")}</span>
                    <span className="figure w-12 text-right text-slate-900">{count}</span>
                    <span className="figure text-xs text-slate-400">
                      {pct(requests.total > 0 ? count / requests.total : 0)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>

        {/* --------------------------------------------------- is it fast -- */}
        <Section
          id="fast"
          question="Is it fast?"
          hint={
            <>
              <strong className="font-semibold text-slate-700">The reranker owns p95.</strong> It is{" "}
              <span className="figure">{pct(rerankShare)}</span> of mean latency — the one stage
              worth optimising, and the first to drop under load.
            </>
          }
        >
          <div className="grid gap-3 lg:grid-cols-[repeat(2,minmax(0,1fr))_minmax(0,1.6fr)]">
            <MetricCard label="p50" value={ms(latency_ms.p50)} note="typical request" compact />
            <MetricCard
              label="p95"
              value={ms(latency_ms.p95)}
              note="target: under 3s for the whole request"
              tone={latency_ms.p95 > 3000 ? "bad" : "good"}
              compact
            />
            <StageBars
              stages={[
                { name: "retrieval", ms: latency_ms.mean_retrieval },
                { name: "rerank", ms: latency_ms.mean_rerank },
                { name: "generation", ms: latency_ms.mean_generation },
              ]}
            />
          </div>
        </Section>

        {/* -------------------------------------------- is it trustworthy -- */}
        <Section
          id="trustworthy"
          question="Is it trustworthy?"
          hint="Satisfaction is computed over rated answers only, so at low volume a single vote moves it several points — read the direction, not the decimal."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Satisfaction"
              value={quality.thumbs_up + quality.thumbs_down > 0 ? pct(quality.satisfaction_rate) : "—"}
              note={`${quality.thumbs_up} up · ${quality.thumbs_down} down`}
              tone={quality.satisfaction_rate >= 0.8 ? "good" : "neutral"}
            />
            <MetricCard
              label="Fabricated citations"
              value={quality.answers_with_fabricated_citations}
              note="answers citing a source that was never offered"
              tone={quality.answers_with_fabricated_citations > 0 ? "bad" : "good"}
            />
            <MetricCard
              label="Mean confidence"
              value={quality.mean_confidence.toFixed(3)}
              note="averages two scales ~30x apart — a trend, not an absolute"
            />
            <MetricCard
              label="Open escalations"
              value={escalations.open}
              note="a rising count is a corpus gap, not a fault"
              tone={escalations.open > 0 ? "warn" : "good"}
            />
          </div>

          {Object.keys(escalations.by_reason).length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3.5">
              <p className="text-2xs font-semibold uppercase tracking-[0.1em] text-amber-700">
                Open escalations by reason
              </p>
              <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1.5">
                {Object.entries(escalations.by_reason).map(([reason, count]) => (
                  <li key={reason} className="text-sm text-amber-900">
                    {reason.replace(/_/g, " ")}{" "}
                    <span className="figure font-semibold">{count}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2.5 text-xs leading-relaxed text-amber-800">
                Amber, not rose: an abstention is the confidence gate doing its job. A rising count
                means the corpus has a gap, not that the system is broken.
              </p>
            </div>
          )}
        </Section>

        {/* ------------------------------------------------ is it leaking -- */}
        {by_tenant.length > 0 && (
          <Section
            id="leaking"
            question="Is it leaking?"
            hint="Every tenant's traffic is counted separately because every tenant's corpus is stored separately. A row appearing here that should not exist is the leak signal; the numbers themselves are just volume."
          >
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[36rem] text-sm">
                <thead className="border-b border-line bg-surface-sunken text-2xs uppercase tracking-[0.08em] text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Tenant</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Requests</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Escalation</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Cache hits</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">p95</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {by_tenant.map((row) => (
                    <tr key={row.tenant_id}>
                      <td className="px-4 py-2 font-medium text-slate-900">{row.tenant_id}</td>
                      <td className="figure px-4 py-2 text-right text-slate-700">{row.requests}</td>
                      <td className="figure px-4 py-2 text-right text-slate-700">{pct(row.escalation_rate)}</td>
                      <td className="figure px-4 py-2 text-right text-slate-700">{pct(row.cache_hit_rate)}</td>
                      <td className="figure px-4 py-2 text-right text-slate-700">{ms(row.p95_ms)}</td>
                      <td className="figure px-4 py-2 text-right text-slate-700">${row.cost_usd.toFixed(5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {/* ----------------------------------------------- what it costs -- */}
        <Section
          id="cost"
          question="What would it cost?"
          hint="Free tiers are the constraint this project is engineered around. The fallback chain exists so one exhausted provider does not stop the system."
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Total this window" value={`$${cost.total_usd.toFixed(5)}`} note="virtual" compact />
            <MetricCard label="Tokens in" value={cost.tokens_in.toLocaleString()} note="prompt + context" compact />
            <MetricCard label="Tokens out" value={cost.tokens_out.toLocaleString()} note="generated answers" compact />
            <MetricCard label="Real spend" value="$0.00" note="every provider is on a free tier" tone="good" compact />
          </div>

          {Object.keys(providers).length > 0 && typeof providers.error !== "string" && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(providers).map(([name, usage]) => {
                if (typeof usage === "string") return null;
                return (
                  <MetricCard
                    key={name}
                    label={name}
                    value={usage.requests ?? 0}
                    note={`${((usage.tokens_in ?? 0) + (usage.tokens_out ?? 0)).toLocaleString()} tokens · $${(usage.virtual_cost_usd ?? 0).toFixed(5)}`}
                    compact
                  />
                );
              })}
            </div>
          )}

          {/* The methodology label stays attached to the figures. Detached from
              it, "cost" on this page reads as a bill. */}
          <p className="mt-3 rounded-lg border border-line bg-surface-sunken px-4 py-3 text-xs leading-relaxed text-slate-600">
            <strong className="font-semibold text-slate-800">Virtual cost.</strong> What this usage{" "}
            <em>would</em> cost at paid-API list prices, priced per token from the model that served
            each request. Fishack runs on free tiers, so real spend is $0.00. The figure exists to
            make the cost of a design choice visible before it is a bill.{" "}
            <span className="text-slate-500">{cost.methodology}</span>
          </p>
        </Section>
      </div>
    </div>
  );
}
