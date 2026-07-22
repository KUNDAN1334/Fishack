"""The corpus skeleton: every document, changelog entry, and ticket declared
explicitly.

Why declare rather than randomly generate: the eval golden set (Phase 4)
needs to KNOW which chunks are the right answer to which query, which docs
are stale, and which error codes exist. A random corpus makes the golden set
unverifiable. Everything the evals depend on is pinned here.

Two tenants share most docs (each gets its own rows — see interview_prep Q5)
plus a few tenant-specific ones.

STALE-DATA DESIGN (Design.md §3, §11a) — we plant two DIFFERENT kinds of
conflict, because they exercise different defenses:

  1. SUPERSEDED (`supersedes` on a changelog entry): ingestion flips the old
     doc's `is_current=false`. Retrieval never sees it. Tests the *ingestion*
     defense — "stale data hallucination ka root cause missing metadata hai".

  2. UNMARKED CONFLICT (`conflicts_with`): the old doc stays `is_current=true`
     but a newer changelog contradicts it. Both are retrievable. Tests the
     *generation* defense — Design.md §7 rule 4: prefer the newest source and
     flag the discrepancy. This is the realistic case, because in production
     nobody remembers to mark the old doc.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

TENANTS: dict[str, str] = {
    "acme": "Acme Corp",
    "globex": "Globex Industries",
}

PRODUCT_AREAS = ("analytics", "billing", "platform")


@dataclass(frozen=True)
class SectionSpec:
    """One H2/H3 section of a doc page. `hint` steers the LLM; `table`
    requests a markdown table (chunker edge case we explicitly want in the
    corpus)."""

    heading: str
    hint: str
    subsections: tuple[tuple[str, str], ...] = ()  # (H3 heading, hint)
    table: tuple[str, ...] | None = None  # column headers
    long: bool = False  # ask for a deliberately long section (splitting test)


@dataclass(frozen=True)
class DocSpec:
    slug: str
    title: str
    product_area: str
    version: str
    effective_date: dt.date
    sections: tuple[SectionSpec, ...]
    tenant: str | None = None  # None = shared by all tenants


@dataclass(frozen=True)
class ChangelogSpec:
    entry_id: str
    version: str
    date: dt.date
    title: str
    kind: str  # 'added' | 'changed' | 'fixed' | 'deprecated'
    hint: str
    product_area: str
    tenant: str | None = None
    # Doc slug this entry makes obsolete -> ingestion sets is_current=false
    supersedes: str | None = None
    # Doc slug this entry contradicts, but which stays live (unmarked conflict)
    conflicts_with: str | None = None


@dataclass(frozen=True)
class TicketSpec:
    ticket_id: str
    tenant: str
    subject: str
    question_hint: str
    answer_hint: str
    product_area: str
    resolution_tag: str  # 'config' | 'bug' | 'user_error' | 'docs' | 'billing'
    error_code: str | None = None
    resolved_date: dt.date = dt.date(2026, 5, 1)


D = dt.date


# ---------------------------------------------------------------------------
# PRODUCT DOCS — 26 shared (x2 tenants = 52) + 4 acme + 4 globex = 60 pages
# ---------------------------------------------------------------------------

SHARED_DOCS: tuple[DocSpec, ...] = (
    DocSpec(
        "webhooks-overview", "Webhooks Overview", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Introduction", "what Flowlytics webhooks are, push-based event delivery over HTTPS POST"),
            SectionSpec("Event Types", "list of event types the platform emits",
                        table=("Event", "Trigger", "Payload version")),
            SectionSpec("Delivery Guarantees", "at-least-once delivery, ordering not guaranteed, idempotency keys"),
            SectionSpec("Retry Logic", "exponential backoff, MAXIMUM 3 RETRY ATTEMPTS, 30 second initial delay, "
                                       "state this 3-attempt limit explicitly and concretely",
                        subsections=(("Backoff Schedule", "the delay between each of the 3 attempts"),
                                     ("Dead Letter Queue", "where undeliverable events go after retries exhaust"))),
        ),
    ),
    DocSpec(
        "webhooks-security", "Webhook Security", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Signature Verification", "HMAC-SHA256 signature in the X-Flowlytics-Signature header"),
            SectionSpec("Secret Rotation", "rotating the signing secret without downtime, dual-secret window"),
            SectionSpec("IP Allowlisting", "static egress IP ranges customers can allowlist",
                        table=("Region", "IP range", "Since")),
        ),
    ),
    DocSpec(
        "api-authentication", "API Authentication", "platform", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("API Keys", "creating, scoping and revoking API keys in the dashboard"),
            SectionSpec("Bearer Token Usage", "Authorization header format and a curl example"),
            SectionSpec("Key Rotation", "zero-downtime rotation procedure"),
            SectionSpec("Scopes and Permissions", "read/write scopes per resource",
                        table=("Scope", "Grants", "Required plan")),
        ),
    ),
    DocSpec(
        "api-rate-limits", "API Rate Limits", "platform", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("Default Limits", "the per-plan request ceilings, state 1,000 requests per minute on "
                                          "Growth plan explicitly",
                        table=("Plan", "Requests/min", "Burst")),
            SectionSpec("Rate Limit Headers", "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"),
            SectionSpec("Handling 429 Responses", "ERR_RATE_LIMITED error code, exponential backoff guidance, "
                                                  "mention the error code explicitly"),
        ),
    ),
    DocSpec(
        "api-errors", "API Error Reference", "platform", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("Error Response Format", "JSON error envelope with code, message, request_id"),
            SectionSpec("Error Code Catalog", "catalog of platform error codes, MUST include ERR_TIMEOUT_502 "
                                              "(upstream gateway timeout), ERR_RATE_LIMITED, ERR_INVALID_KEY, "
                                              "ERR_SCHEMA_MISMATCH",
                        table=("Code", "HTTP status", "Meaning", "Action"), long=True),
            SectionSpec("Retryable vs Terminal Errors", "which error codes are safe to retry"),
        ),
    ),
    DocSpec(
        "data-ingestion-api", "Data Ingestion API", "analytics", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("Sending Events", "POST /v2/events endpoint, batch and single modes"),
            SectionSpec("Batch Limits", "maximum 500 events per batch request, 5 MB payload ceiling"),
            SectionSpec("Schema Validation", "ERR_SCHEMA_MISMATCH when a property type changes"),
            SectionSpec("Idempotency", "dedup window based on event_id"),
        ),
    ),
    DocSpec(
        "data-sync-latency", "Data Sync and Latency", "analytics", "v2.0", D(2026, 1, 15),
        (
            SectionSpec("Ingestion Pipeline Stages", "how an event travels from API to queryable storage"),
            SectionSpec("Expected Latency", "state clearly that events appear in dashboards within 15 minutes"),
            SectionSpec("Synchronization Delays", "common causes of delayed data, backfill behavior"),
            SectionSpec("Monitoring Sync Health", "the pipeline health page and what its statuses mean"),
        ),
    ),
    DocSpec(
        "dashboards-overview", "Dashboards Overview", "analytics", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Creating a Dashboard", "dashboard builder walkthrough"),
            SectionSpec("Widget Types", "chart widget catalog", table=("Widget", "Best for", "Data required")),
            SectionSpec("Sharing and Permissions", "internal sharing, public links, viewer roles"),
        ),
    ),
    DocSpec(
        "custom-metrics", "Custom Metrics", "analytics", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Defining a Metric", "metric builder, aggregation types"),
            SectionSpec("Formula Syntax", "supported operators and functions", long=True),
            SectionSpec("Metric Limits", "50 custom metrics per workspace on Growth plan"),
        ),
    ),
    DocSpec(
        "segments-and-cohorts", "Segments and Cohorts", "analytics", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("Building a Segment", "filter builder and boolean logic"),
            SectionSpec("Cohort Retention Analysis", "how retention grids are computed"),
            SectionSpec("Segment Refresh Cadence", "segments recompute hourly"),
        ),
    ),
    DocSpec(
        "query-engine", "Query Engine", "analytics", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("Query Language Basics", "the Flowlytics query syntax"),
            SectionSpec("Query Timeouts", "queries time out after 30 seconds and return ERR_TIMEOUT_502"),
            SectionSpec("Optimizing Slow Queries", "indexing hints, narrowing time ranges", long=True),
        ),
    ),
    DocSpec(
        "data-export", "Data Export", "analytics", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Export Formats", "CSV, JSON, Parquet", table=("Format", "Max rows", "Compression")),
            SectionSpec("Scheduled Exports", "cron-style scheduling to S3 or GCS"),
            SectionSpec("Export Retention", "export files are retained for 7 days"),
        ),
    ),
    DocSpec(
        "billing-plans", "Billing Plans", "billing", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Plan Comparison", "Starter, Growth, Enterprise",
                        table=("Plan", "Monthly price", "Events included", "Seats")),
            SectionSpec("Plan Limits", "what happens at the event ceiling"),
            SectionSpec("Upgrading and Downgrading", "when plan changes take effect"),
        ),
    ),
    DocSpec(
        "billing-invoices", "Invoices", "billing", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("Invoice Generation", "invoices generate on the first of the month"),
            SectionSpec("Proration", "how mid-cycle plan changes are prorated, daily proration basis", long=True),
            SectionSpec("Invoice Delivery", "email recipients and PDF download"),
        ),
    ),
    DocSpec(
        "billing-usage-metering", "Usage Metering", "billing", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("What Counts as a Billable Event", "billable vs free event types"),
            SectionSpec("Metering Window", "usage is metered on a UTC calendar month"),
            SectionSpec("Overage Charges", "state the overage rate as $0.10 per 1,000 events over the plan limit",
                        table=("Plan", "Included events", "Overage per 1k")),
        ),
    ),
    DocSpec(
        "billing-payment-methods", "Payment Methods", "billing", "v2.0", D(2026, 1, 15),
        (
            SectionSpec("Supported Methods", "credit card, ACH, wire for Enterprise"),
            SectionSpec("Failed Payments", "ERR_PAYMENT_DECLINED, dunning schedule, retry attempts"),
            SectionSpec("Updating a Card", "self-serve card update flow"),
        ),
    ),
    DocSpec(
        "billing-tax", "Tax and Compliance", "billing", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("VAT and Sales Tax", "how tax is determined by billing address"),
            SectionSpec("Tax Exemption", "submitting an exemption certificate"),
            SectionSpec("Invoices for Compliance", "what compliance fields invoices carry"),
        ),
    ),
    DocSpec(
        "sso-setup", "SSO Setup", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("SAML Configuration", "IdP metadata exchange steps"),
            SectionSpec("SCIM Provisioning", "automated user provisioning and deprovisioning"),
            SectionSpec("Troubleshooting SSO", "common assertion errors", long=True),
        ),
    ),
    DocSpec(
        "user-roles", "Users and Roles", "platform", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("Role Types", "Owner, Admin, Analyst, Viewer",
                        table=("Role", "Can edit dashboards", "Can manage billing", "Can invite")),
            SectionSpec("Inviting Users", "invitation flow and expiry"),
            SectionSpec("Removing Users", "what happens to a removed user's dashboards"),
        ),
    ),
    DocSpec(
        "audit-logs", "Audit Logs", "platform", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("What Is Logged", "authentication, configuration and data-access events"),
            SectionSpec("Retention Period", "audit logs are retained for 90 days"),
            SectionSpec("Exporting Audit Logs", "API and scheduled export options"),
        ),
    ),
    DocSpec(
        "integrations-overview", "Integrations Overview", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Available Integrations", "Slack, Salesforce, Snowflake, Segment",
                        table=("Integration", "Direction", "Sync frequency")),
            SectionSpec("Connecting an Integration", "OAuth connection flow"),
            SectionSpec("Integration Health", "how failures surface"),
        ),
    ),
    DocSpec(
        "integrations-snowflake", "Snowflake Integration", "analytics", "v2.3", D(2026, 4, 2),
        (
            SectionSpec("Setup", "warehouse, role and credential requirements"),
            SectionSpec("Sync Schedule", "hourly incremental syncs"),
            SectionSpec("Troubleshooting Sync Failures", "permission errors and schema drift", long=True),
        ),
    ),
    DocSpec(
        "sdk-javascript", "JavaScript SDK", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Installation", "npm install and script tag options"),
            SectionSpec("Initialization", "init options and the write key"),
            SectionSpec("Tracking Events", "track, identify, page methods with examples", long=True),
        ),
    ),
    DocSpec(
        "sdk-python", "Python SDK", "platform", "v2.1", D(2026, 2, 18),
        (
            SectionSpec("Installation", "pip install flowlytics"),
            SectionSpec("Client Configuration", "timeouts, batching, retries"),
            SectionSpec("Async Usage", "asyncio client and flush semantics"),
        ),
    ),
    DocSpec(
        "data-retention", "Data Retention", "platform", "v2.0", D(2026, 1, 15),
        (
            SectionSpec("Retention by Plan", "state clearly that raw event data is retained for 12 months "
                                             "on the Growth plan",
                        table=("Plan", "Raw events", "Aggregates")),
            SectionSpec("Deletion Requests", "GDPR deletion request handling"),
            SectionSpec("Archival Storage", "cold storage for older data"),
        ),
    ),
    DocSpec(
        "troubleshooting-guide", "Troubleshooting Guide", "platform", "v2.2", D(2026, 3, 12),
        (
            SectionSpec("Data Not Appearing", "checklist when events do not show up"),
            SectionSpec("Authentication Failures", "ERR_INVALID_KEY causes"),
            SectionSpec("Slow Dashboards", "diagnosing slow dashboard loads", long=True),
            SectionSpec("Getting Support", "how to contact support and what to include"),
        ),
    ),
)

TENANT_DOCS: tuple[DocSpec, ...] = (
    DocSpec(
        "acme-onboarding-runbook", "Acme Onboarding Runbook", "platform", "v1.0", D(2026, 2, 4),
        (
            SectionSpec("Acme Workspace Layout", "how Acme's three workspaces map to business units"),
            SectionSpec("Acme Naming Conventions", "the acme_ event prefix convention"),
            SectionSpec("Escalation Contacts", "Acme's named CSM and escalation path"),
        ),
        tenant="acme",
    ),
    DocSpec(
        "acme-custom-sla", "Acme Service Level Agreement", "platform", "v1.2", D(2026, 3, 20),
        (
            SectionSpec("Uptime Commitment", "99.95% uptime commitment specific to Acme"),
            SectionSpec("Support Response Times", "Acme P1 response within 30 minutes",
                        table=("Severity", "Response", "Resolution target")),
            SectionSpec("Service Credits", "credit schedule for missed SLA"),
        ),
        tenant="acme",
    ),
    DocSpec(
        "acme-data-residency", "Acme Data Residency", "platform", "v1.1", D(2026, 3, 1),
        (
            SectionSpec("EU Region Pinning", "Acme data is pinned to the eu-central region"),
            SectionSpec("Cross-Region Restrictions", "what cannot leave the region"),
        ),
        tenant="acme",
    ),
    DocSpec(
        "acme-billing-terms", "Acme Billing Terms", "billing", "v1.0", D(2026, 1, 20),
        (
            SectionSpec("Negotiated Rates", "Acme's negotiated annual commit and rate card"),
            SectionSpec("Purchase Order Process", "Acme requires a PO number on every invoice"),
        ),
        tenant="acme",
    ),
    DocSpec(
        "globex-onboarding-runbook", "Globex Onboarding Runbook", "platform", "v1.0", D(2026, 2, 11),
        (
            SectionSpec("Globex Workspace Layout", "Globex's single-workspace multi-project setup"),
            SectionSpec("Globex Naming Conventions", "the gbx. event namespace convention"),
            SectionSpec("Escalation Contacts", "Globex's escalation path through their platform team"),
        ),
        tenant="globex",
    ),
    DocSpec(
        "globex-custom-sla", "Globex Service Level Agreement", "platform", "v1.1", D(2026, 3, 20),
        (
            SectionSpec("Uptime Commitment", "99.9% uptime commitment specific to Globex"),
            SectionSpec("Support Response Times", "Globex P1 response within 2 hours",
                        table=("Severity", "Response", "Resolution target")),
            SectionSpec("Service Credits", "credit schedule for missed SLA"),
        ),
        tenant="globex",
    ),
    DocSpec(
        "globex-private-link", "Globex PrivateLink Setup", "platform", "v1.0", D(2026, 2, 25),
        (
            SectionSpec("PrivateLink Endpoints", "Globex-only AWS PrivateLink connectivity"),
            SectionSpec("DNS Configuration", "private DNS records required"),
        ),
        tenant="globex",
    ),
    DocSpec(
        "globex-billing-terms", "Globex Billing Terms", "billing", "v1.0", D(2026, 1, 28),
        (
            SectionSpec("Negotiated Rates", "Globex's quarterly commit structure"),
            SectionSpec("Consolidated Invoicing", "Globex receives one consolidated invoice per quarter"),
        ),
        tenant="globex",
    ),
)

ALL_DOCS: tuple[DocSpec, ...] = SHARED_DOCS + TENANT_DOCS


# ---------------------------------------------------------------------------
# CHANGELOG — 40 entries, v2.0 -> v2.4
# The conflicts below are the heart of the stale-data demo.
# ---------------------------------------------------------------------------

CHANGELOG: tuple[ChangelogSpec, ...] = (
    # ---- v2.4 (2026-06-10): the headline conflicts --------------------------
    ChangelogSpec(
        "CL-2026-0610-01", "v2.4", D(2026, 6, 10), "Webhook retry limit increased to 5 attempts", "changed",
        "webhook retries now attempt up to 5 times instead of 3, with a longer backoff tail; "
        "state the new limit of 5 attempts explicitly",
        "platform",
        # UNMARKED conflict: webhooks-overview still says 3 and stays is_current.
        # The generator must prefer this entry AND flag the discrepancy.
        conflicts_with="webhooks-overview",
    ),
    ChangelogSpec(
        "CL-2026-0610-02", "v2.4", D(2026, 6, 10), "Data sync latency reduced to 5 minutes", "changed",
        "the ingestion pipeline now surfaces events in dashboards within 5 minutes instead of 15; "
        "state the new 5 minute figure explicitly",
        "analytics",
        conflicts_with="data-sync-latency",
    ),
    ChangelogSpec(
        "CL-2026-0610-03", "v2.4", D(2026, 6, 10), "Legacy v1 export endpoints removed", "deprecated",
        "the deprecated /v1/export endpoints are removed; customers must migrate to /v2/export",
        "analytics", supersedes="data-export",
    ),
    ChangelogSpec(
        "CL-2026-0610-04", "v2.4", D(2026, 6, 10), "Overage rate reduced to $0.08 per 1,000 events", "changed",
        "the overage rate drops from $0.10 to $0.08 per 1,000 events; state the new rate explicitly",
        "billing", conflicts_with="billing-usage-metering",
    ),
    ChangelogSpec(
        "CL-2026-0610-05", "v2.4", D(2026, 6, 10), "Query timeout raised to 60 seconds", "changed",
        "long-running queries may now run for 60 seconds before returning ERR_TIMEOUT_502, up from 30",
        "analytics", conflicts_with="query-engine",
    ),
    ChangelogSpec(
        "CL-2026-0610-06", "v2.4", D(2026, 6, 10), "Dashboard widget: funnel comparison", "added",
        "new funnel comparison widget for comparing two segments side by side", "analytics"),
    ChangelogSpec(
        "CL-2026-0610-07", "v2.4", D(2026, 6, 10), "Fixed duplicate webhook deliveries", "fixed",
        "a race condition in the delivery worker caused occasional duplicate webhook deliveries", "platform"),
    ChangelogSpec(
        "CL-2026-0610-08", "v2.4", D(2026, 6, 10), "SCIM group sync", "added",
        "SCIM now syncs group membership, not just users", "platform"),

    # ---- v2.3 (2026-04-02) --------------------------------------------------
    ChangelogSpec("CL-2026-0402-01", "v2.3", D(2026, 4, 2), "New error code ERR_SCHEMA_MISMATCH", "added",
                  "events whose property types conflict with the existing schema now return ERR_SCHEMA_MISMATCH "
                  "instead of being silently dropped", "analytics"),
    ChangelogSpec("CL-2026-0402-02", "v2.3", D(2026, 4, 2), "Audit log export API", "added",
                  "audit logs can now be exported via API", "platform"),
    ChangelogSpec("CL-2026-0402-03", "v2.3", D(2026, 4, 2), "Snowflake integration GA", "added",
                  "the Snowflake integration leaves beta", "analytics"),
    ChangelogSpec("CL-2026-0402-04", "v2.3", D(2026, 4, 2), "API key scopes", "added",
                  "API keys can now be scoped to specific resources", "platform"),
    ChangelogSpec("CL-2026-0402-05", "v2.3", D(2026, 4, 2), "Batch size limit raised to 500 events", "changed",
                  "ingestion batches may now contain 500 events, up from 250", "analytics"),
    ChangelogSpec("CL-2026-0402-06", "v2.3", D(2026, 4, 2), "Fixed proration rounding error", "fixed",
                  "mid-cycle upgrades occasionally rounded proration up by one day", "billing"),
    ChangelogSpec("CL-2026-0402-07", "v2.3", D(2026, 4, 2), "Usage metering dashboard", "added",
                  "a real-time usage meter in the billing settings page", "billing"),
    ChangelogSpec("CL-2026-0402-08", "v2.3", D(2026, 4, 2), "Improved ERR_TIMEOUT_502 diagnostics", "changed",
                  "gateway timeout responses now include the request_id and the stage that timed out", "platform"),

    # ---- v2.2 (2026-03-12) --------------------------------------------------
    ChangelogSpec("CL-2026-0312-01", "v2.2", D(2026, 3, 12), "Webhook signature verification", "added",
                  "webhooks are now signed with HMAC-SHA256", "platform"),
    ChangelogSpec("CL-2026-0312-02", "v2.2", D(2026, 3, 12), "Dashboard public links", "added",
                  "dashboards can be shared via read-only public links", "analytics"),
    ChangelogSpec("CL-2026-0312-03", "v2.2", D(2026, 3, 12), "Custom metric formula functions", "added",
                  "new formula functions for percentile and rate calculations", "analytics"),
    ChangelogSpec("CL-2026-0312-04", "v2.2", D(2026, 3, 12), "Parquet export format", "added",
                  "exports can now be written as Parquet", "analytics"),
    ChangelogSpec("CL-2026-0312-05", "v2.2", D(2026, 3, 12), "Slack integration rebuilt", "changed",
                  "the Slack integration moved to the new OAuth app model", "platform"),
    ChangelogSpec("CL-2026-0312-06", "v2.2", D(2026, 3, 12), "Fixed segment refresh stalling", "fixed",
                  "segments with more than 40 filters could stall during hourly refresh", "analytics"),
    ChangelogSpec("CL-2026-0312-07", "v2.2", D(2026, 3, 12), "JavaScript SDK v3", "changed",
                  "the JS SDK moves to a smaller ES module build", "platform"),
    ChangelogSpec("CL-2026-0312-08", "v2.2", D(2026, 3, 12), "Invoice PDF redesign", "changed",
                  "invoices carry clearer line items for overages", "billing"),

    # ---- v2.1 (2026-02-18) --------------------------------------------------
    ChangelogSpec("CL-2026-0218-01", "v2.1", D(2026, 2, 18), "Rate limit headers added", "added",
                  "all API responses now include X-RateLimit-* headers", "platform"),
    ChangelogSpec("CL-2026-0218-02", "v2.1", D(2026, 2, 18), "Cohort retention grids", "added",
                  "retention analysis by cohort", "analytics"),
    ChangelogSpec("CL-2026-0218-03", "v2.1", D(2026, 2, 18), "Analyst role introduced", "added",
                  "a new Analyst role between Admin and Viewer", "platform"),
    ChangelogSpec("CL-2026-0218-04", "v2.1", D(2026, 2, 18), "Tax exemption certificates", "added",
                  "self-serve upload of tax exemption certificates", "billing"),
    ChangelogSpec("CL-2026-0218-05", "v2.1", D(2026, 2, 18), "Python SDK async client", "added",
                  "an asyncio-native client in the Python SDK", "platform"),
    ChangelogSpec("CL-2026-0218-06", "v2.1", D(2026, 2, 18), "Fixed ERR_INVALID_KEY on rotated keys", "fixed",
                  "recently rotated keys could return ERR_INVALID_KEY for up to 60 seconds", "platform"),
    ChangelogSpec("CL-2026-0218-07", "v2.1", D(2026, 2, 18), "Segment refresh moved to hourly", "changed",
                  "segments refresh hourly instead of every six hours", "analytics"),
    ChangelogSpec("CL-2026-0218-08", "v2.1", D(2026, 2, 18), "ACH payments supported", "added",
                  "ACH is available as a payment method for US customers", "billing"),

    # ---- v2.0 (2026-01-15) --------------------------------------------------
    ChangelogSpec("CL-2026-0115-01", "v2.0", D(2026, 1, 15), "Flowlytics v2 platform release", "changed",
                  "the v2 API is generally available with a new event schema", "platform"),
    ChangelogSpec("CL-2026-0115-02", "v2.0", D(2026, 1, 15), "Query engine rewrite", "changed",
                  "a columnar query engine replaces the v1 row store", "analytics"),
    ChangelogSpec("CL-2026-0115-03", "v2.0", D(2026, 1, 15), "Data retention controls", "added",
                  "per-plan retention settings in the workspace settings page", "platform"),
    ChangelogSpec("CL-2026-0115-04", "v2.0", D(2026, 1, 15), "SAML SSO", "added",
                  "SAML-based single sign-on for Enterprise plans", "platform"),
    ChangelogSpec("CL-2026-0115-05", "v2.0", D(2026, 1, 15), "Usage-based billing", "changed",
                  "billing moves from seat-based to usage-based metering", "billing"),
    ChangelogSpec("CL-2026-0115-06", "v2.0", D(2026, 1, 15), "Deprecated v1 SDKs", "deprecated",
                  "v1 SDKs enter maintenance mode", "platform"),

    # ---- tenant-specific ----------------------------------------------------
    ChangelogSpec("CL-2026-0415-AC", "v2.3", D(2026, 4, 15), "Acme EU region migration complete", "changed",
                  "Acme's workspaces are fully migrated to eu-central", "platform", tenant="acme"),
    ChangelogSpec("CL-2026-0501-GX", "v2.3", D(2026, 5, 1), "Globex PrivateLink endpoints live", "added",
                  "PrivateLink endpoints are live in us-east and eu-west for Globex", "platform", tenant="globex"),
)


# ---------------------------------------------------------------------------
# SUPPORT TICKETS — 50 resolved Q&A pairs (25 per tenant)
# Error codes appear verbatim: these are the exact-identifier eval cases where
# BM25 must beat vector search (Design.md §5).
# ---------------------------------------------------------------------------

def _t(
    n: int, tenant: str, subject: str, q: str, a: str, area: str, tag: str,
    error_code: str | None = None, month: int = 5, day: int = 1,
) -> TicketSpec:
    prefix = "ACM" if tenant == "acme" else "GBX"
    return TicketSpec(f"{prefix}-{n:04d}", tenant, subject, q, a, area, tag, error_code,
                      D(2026, month, day))


TICKETS: tuple[TicketSpec, ...] = (
    # ---------------------------- acme ------------------------------------
    _t(1041, "acme", "Webhooks failing after v2.3 upgrade",
       "customer's webhook endpoint started returning 502s after upgrading, asks why deliveries stopped",
       "their endpoint was timing out past 10s; Flowlytics marks slow endpoints as failed and retries. "
       "Fix was to acknowledge the webhook immediately and process asynchronously",
       "platform", "config", "ERR_TIMEOUT_502", 5, 3),
    _t(1042, "acme", "ERR_RATE_LIMITED during backfill",
       "hitting rate limits while backfilling historical events",
       "backfill was running 40 parallel workers; advised batching 500 events per request and "
       "respecting X-RateLimit-Remaining", "platform", "user_error", "ERR_RATE_LIMITED", 5, 4),
    _t(1043, "acme", "Events missing from dashboard",
       "events sent successfully but not visible in the dashboard after 20 minutes",
       "events were sent with a timestamp outside the dashboard's selected time range", "analytics",
       "user_error", None, 5, 6),
    _t(1044, "acme", "ERR_SCHEMA_MISMATCH on user_id property",
       "ingestion started rejecting events with ERR_SCHEMA_MISMATCH",
       "user_id had been sent as an integer historically and the client began sending strings; "
       "resolved by casting to string at the SDK layer", "analytics", "bug", "ERR_SCHEMA_MISMATCH", 5, 7),
    _t(1045, "acme", "Invoice shows unexpected overage",
       "invoice included an overage charge the customer did not expect",
       "a test workspace was emitting billable events; excluded it and issued a credit", "billing",
       "billing", None, 5, 8),
    _t(1046, "acme", "SAML login loop",
       "users bounced between the IdP and Flowlytics without logging in",
       "the IdP was sending an unexpected NameID format; corrected to emailAddress", "platform",
       "config", None, 5, 9),
    _t(1047, "acme", "API key stopped working after rotation",
       "rotated an API key and immediately got ERR_INVALID_KEY",
       "propagation takes up to 60 seconds after rotation; retry after a minute", "platform",
       "user_error", "ERR_INVALID_KEY", 5, 11),
    _t(1048, "acme", "Snowflake sync failing silently",
       "Snowflake integration shows healthy but no new rows arrive",
       "the warehouse role lost USAGE on the target schema after a Snowflake-side change", "analytics",
       "config", None, 5, 12),
    _t(1049, "acme", "Custom metric formula returns null",
       "a custom metric shows null for all periods",
       "the formula divided by a metric that was zero in every period; added a guard", "analytics",
       "user_error", None, 5, 13),
    _t(1050, "acme", "Slow dashboard load with 30 widgets",
       "dashboard takes over a minute to load",
       "reduced to 12 widgets and narrowed default time range; each widget issues its own query",
       "analytics", "user_error", None, 5, 14),
    _t(1051, "acme", "Duplicate webhook deliveries",
       "receiving the same webhook event twice",
       "known race condition fixed in v2.4; interim workaround is to dedupe on event_id", "platform",
       "bug", None, 5, 15),
    _t(1052, "acme", "PO number missing from invoice",
       "Acme's finance team rejected an invoice with no PO number",
       "the PO field was blank on the billing profile; added it and reissued", "billing", "billing", None, 5, 16),
    _t(1053, "acme", "Data residency question for EU region",
       "asks whether analytics query results leave eu-central",
       "query execution and storage stay in-region for Acme; only aggregate telemetry leaves", "platform",
       "docs", None, 5, 18),
    _t(1054, "acme", "Export file expired before download",
       "scheduled export link returned 404",
       "export files are retained 7 days; re-ran the export and advised automating the download",
       "analytics", "user_error", None, 5, 19),
    _t(1055, "acme", "Segment not updating after filter change",
       "edited a segment but counts did not change",
       "segments recompute hourly; the change was visible on the next refresh", "analytics",
       "user_error", None, 5, 20),
    _t(1056, "acme", "SCIM deprovisioning did not remove access",
       "a deactivated employee still had dashboard access",
       "the SCIM connector was scoped to a group that did not include the user", "platform", "config", None, 5, 21),
    _t(1057, "acme", "Which events are billable?",
       "asks whether identify calls count toward the plan limit",
       "identify and page calls are billable; only internal system events are free", "billing", "docs", None, 5, 22),
    _t(1058, "acme", "Query returns ERR_TIMEOUT_502 on 90-day range",
       "a 90-day query consistently times out",
       "narrowed the range and pre-aggregated with a custom metric; 30s query ceiling at the time",
       "analytics", "user_error", "ERR_TIMEOUT_502", 5, 23),
    _t(1059, "acme", "P1 escalation path unclear",
       "asks who to contact for a production outage at 2am",
       "documented Acme's 30-minute P1 response path via the on-call rotation", "platform", "docs", None, 5, 25),
    _t(1060, "acme", "Webhook signature verification failing",
       "computed HMAC does not match the header",
       "customer was hashing the parsed JSON rather than the raw request body", "platform",
       "user_error", None, 5, 26),
    _t(1061, "acme", "Proration seems wrong after upgrade",
       "mid-month upgrade produced a larger charge than expected",
       "proration is daily; the upgrade landed on day 4 of the cycle so 27 days were charged at the new rate",
       "billing", "billing", None, 5, 27),
    _t(1062, "acme", "Analyst role cannot edit dashboards",
       "an Analyst user could not save dashboard changes",
       "Analyst can create but not edit shared dashboards; moved the user to Admin", "platform",
       "user_error", None, 5, 28),
    _t(1063, "acme", "Audit log missing an event",
       "an admin action did not appear in audit logs",
       "the action predated the 90-day retention window", "platform", "docs", None, 5, 29),
    _t(1064, "acme", "Batch request rejected at 600 events",
       "batch POST returned an error at 600 events",
       "batch ceiling is 500 events per request; split the batch", "analytics", "user_error", None, 5, 30),
    _t(1065, "acme", "ACH payment failed",
       "payment did not go through and the account was flagged",
       "the bank rejected the debit; updated mandate details and re-ran the charge", "billing",
       "billing", "ERR_PAYMENT_DECLINED", 5, 31),

    # --------------------------- globex -----------------------------------
    _t(2041, "globex", "PrivateLink endpoint unreachable",
       "cannot reach the PrivateLink endpoint from their VPC",
       "private DNS was not enabled on the VPC endpoint", "platform", "config", None, 5, 2),
    _t(2042, "globex", "ERR_TIMEOUT_502 on webhook deliveries",
       "webhook receiver intermittently returns gateway timeouts",
       "their load balancer idle timeout was below the delivery time; raised it", "platform",
       "bug", "ERR_TIMEOUT_502", 5, 4),
    _t(2043, "globex", "Consolidated invoice missing a project",
       "quarterly invoice omitted one project's usage",
       "the project was created after the billing period closed; included in the next invoice", "billing",
       "billing", None, 5, 5),
    _t(2044, "globex", "gbx. namespace events not tracked",
       "events under the gbx. prefix are not appearing",
       "the SDK was initialized with the wrong write key for that project", "analytics",
       "user_error", None, 5, 6),
    _t(2045, "globex", "ERR_RATE_LIMITED on Growth plan",
       "hitting rate limits at what they believe is normal volume",
       "Growth plan allows 1,000 requests/min; their client opened a new connection per event", "platform",
       "user_error", "ERR_RATE_LIMITED", 5, 7),
    _t(2046, "globex", "Retention period for raw events",
       "asks how long raw events are kept",
       "12 months of raw events on Growth, aggregates kept longer", "platform", "docs", None, 5, 8),
    _t(2047, "globex", "Snowflake schema drift breaking sync",
       "sync fails after they added a column",
       "schema drift requires re-running the setup step to remap columns", "analytics", "config", None, 5, 10),
    _t(2048, "globex", "Dashboard public link disabled",
       "a shared public dashboard link stopped working",
       "an admin disabled public links workspace-wide for compliance", "analytics", "config", None, 5, 11),
    _t(2049, "globex", "ERR_INVALID_KEY after employee offboarding",
       "integration broke after an employee left",
       "the API key was personally scoped and revoked with the user; created a service key", "platform",
       "config", "ERR_INVALID_KEY", 5, 12),
    _t(2050, "globex", "Funnel numbers differ from their warehouse",
       "funnel counts do not match their own Snowflake numbers",
       "different attribution windows; aligned the funnel window to 7 days", "analytics", "user_error", None, 5, 13),
    _t(2051, "globex", "Are webhook retries guaranteed in order?",
       "asks whether retried webhooks arrive in order",
       "delivery is at-least-once with no ordering guarantee; use event timestamps", "platform",
       "docs", None, 5, 14),
    _t(2052, "globex", "Tax exemption certificate rejected",
       "uploaded exemption certificate was not applied",
       "the certificate had expired; uploaded a current one", "billing", "billing", None, 5, 15),
    _t(2053, "globex", "Query timeout on cohort analysis",
       "cohort retention query times out",
       "reduced cohort granularity from daily to weekly", "analytics", "user_error", "ERR_TIMEOUT_502", 5, 17),
    _t(2054, "globex", "SCIM group sync not supported?",
       "asks whether SCIM can sync groups",
       "group sync shipped in v2.4; before that only user provisioning was supported", "platform",
       "docs", None, 5, 18),
    _t(2055, "globex", "Export to GCS failing with permission error",
       "scheduled export to GCS fails",
       "the service account lacked storage.objectCreator on the bucket", "analytics", "config", None, 5, 19),
    _t(2056, "globex", "Sudden drop in event volume",
       "event volume fell 60% overnight",
       "an ad blocker update began blocking the JS SDK; moved to a first-party proxy endpoint", "analytics",
       "bug", None, 5, 20),
    _t(2057, "globex", "Custom metric limit reached",
       "cannot create a new custom metric",
       "Growth plan caps custom metrics at 50 per workspace; archived unused ones", "analytics",
       "user_error", None, 5, 21),
    _t(2058, "globex", "Invoice delivery to wrong address",
       "invoices going to a former employee",
       "updated the billing contact list", "billing", "billing", None, 5, 22),
    _t(2059, "globex", "Uptime credit request for March incident",
       "requests service credits after a March degradation",
       "confirmed against Globex's 99.9% commitment and applied the credit schedule", "platform",
       "billing", None, 5, 23),
    _t(2060, "globex", "Segment counts differ between dashboard and export",
       "segment count in export does not match the dashboard",
       "the export ran before the hourly segment refresh completed", "analytics", "user_error", None, 5, 24),
    _t(2061, "globex", "Python SDK blocking the event loop",
       "async application stalls when flushing events",
       "they used the sync client inside async code; switched to the asyncio client", "platform",
       "user_error", None, 5, 25),
    _t(2062, "globex", "Data deletion request handling",
       "needs to delete a user's data for GDPR",
       "submitted via the deletion API; processed within 30 days across raw and aggregate stores",
       "platform", "docs", None, 5, 26),
    _t(2063, "globex", "Payment declined on quarterly invoice",
       "the card on file was declined for a large quarterly charge",
       "card had a per-transaction limit; paid by wire instead", "billing", "billing",
       "ERR_PAYMENT_DECLINED", 5, 27),
    _t(2064, "globex", "Which regions have PrivateLink?",
       "asks which regions support PrivateLink",
       "us-east and eu-west are live for Globex as of v2.3", "platform", "docs", None, 5, 28),
    _t(2065, "globex", "Webhook secret rotation caused failures",
       "rotating the signing secret broke verification",
       "both secrets are valid during a 24h dual-secret window; their code only accepted one", "platform",
       "config", None, 5, 29),
)


def docs_for_tenant(tenant: str) -> list[DocSpec]:
    """Shared docs plus that tenant's private docs."""
    return [d for d in ALL_DOCS if d.tenant is None or d.tenant == tenant]


def changelog_for_tenant(tenant: str) -> list[ChangelogSpec]:
    return [c for c in CHANGELOG if c.tenant is None or c.tenant == tenant]


def tickets_for_tenant(tenant: str) -> list[TicketSpec]:
    return [t for t in TICKETS if t.tenant == tenant]


def corpus_summary() -> dict:
    """Counts used by generate_corpus.py output and the Phase 1 walkthrough."""
    return {
        "tenants": len(TENANTS),
        "doc_specs": len(ALL_DOCS),
        "doc_pages_ingested": sum(len(docs_for_tenant(t)) for t in TENANTS),
        "changelog_entries": len(CHANGELOG),
        "changelog_ingested": sum(len(changelog_for_tenant(t)) for t in TENANTS),
        "tickets": len(TICKETS),
        "superseding_entries": sum(1 for c in CHANGELOG if c.supersedes),
        "unmarked_conflicts": sum(1 for c in CHANGELOG if c.conflicts_with),
    }
