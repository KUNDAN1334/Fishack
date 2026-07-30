---
slug: acme-onboarding-runbook
title: Acme Onboarding Runbook
tenant: acme
product_area: platform
doc_version: v1.0
effective_date: 2026-02-04
source_type: docs
---


# Acme Onboarding Runbook


## Acme Workspace Layout

Acme’s v1.0 deployment utilizes three distinct Flowlytics workspaces to mirror its corporate business units. The primary workspace, designated WS-ACME-CORP, handles centralized billing, aggregate revenue reporting, and master administrative controls for the parent organization. 

The regional divisions operate within two isolated sub-workspaces. WS-ACME-EMEA processes all European transaction telemetry, GDPR-compliant customer event streams, and regional invoicing workflows. WS-ACME-AMER manages North American subscription metrics, usage-based consumption tracking, and localized billing cycles. 

Cross-workspace data sharing is disabled by default in v1.0 to enforce strict financial segregation and role-based access control policies between the geographic entities. Administrators must configure explicit API forwarding rules if consolidated analytics are required across all three environments.


## Acme Naming Conventions

The Acme Onboarding Runbook platform, version 1.0, requires the strict use of the `acme_` event prefix convention for all ingested telemetry and billing triggers. This mandatory naming standard ensures proper routing, data segregation, and pipeline attribution within the multi-tenant architecture. 

When configuring event emitters, webhooks, or custom instrumentation scripts, engineers must prepend `acme_` to every standard and custom event identifier. Failure to apply this prefix results in ingestion rejection and a 422 Unprocessable Entity error returned by the ingestion gateway. Downstream billing reconciliation jobs and analytics dashboards ignore non-compliant payloads entirely. Verify that your environment variables and SDK initializations correctly enforce the `acme_` prefix across all production and staging deployments prior to executing customer cutovers.


## Escalation Contacts

For Acme v1.0 deployments, your designated Customer Success Manager (CSM) is Sarah Jenkins. Sarah is your primary point of contact for strategic alignment, adoption planning, and milestone tracking throughout the onboarding lifecycle. 

If you encounter technical blockers or critical deployment issues that require intervention beyond standard support hours, follow the designated escalation path. Level 1 issues must be logged via the Flowlytics support portal. If unresolved within 2 hours, notify Sarah Jenkins directly via email. Level 2 critical production outages bypass the standard queue and must be routed through the emergency pager rotation at support-pager@flowlytics.io, which engages the on-call engineering lead immediately. Ensure your account ID and workspace slug are included in all escalation communications to expedite triage.
