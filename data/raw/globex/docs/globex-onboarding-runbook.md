---
slug: globex-onboarding-runbook
title: Globex Onboarding Runbook
tenant: globex
product_area: platform
doc_version: v1.0
effective_date: 2026-02-11
source_type: docs
---


# Globex Onboarding Runbook


## Globex Workspace Layout

Globex operates under a single-workspace multi-project setup within Flowlytics platform v1.0. This architecture allows the engineering organization to manage isolated data pipelines while maintaining centralized billing and administrative control across all active projects. 

In this configuration, workspace-level permissions apply globally, while project-level keys govern ingestion endpoints and metric routing. Administrators must provision separate project tokens for each development environment to ensure proper data segregation. When configuring the Globex Onboarding Runbook, verify that all downstream webhook subscriptions point to the designated master workspace URL to prevent ingestion drops. Cross-project data aggregation is restricted by default in v1.0 and requires explicit authorization from the primary workspace owner before activation.


## Globex Naming Conventions

All tracking and data ingestion within the Globex Onboarding Runbook (platform, v1.0) must adhere to the standardized gbx. event namespace convention. This naming structure ensures consistent telemetry across all integrated workspaces and prevents collision with native Flowlytics system events. 

When configuring custom instrumentation, every event identifier must begin with the exact prefix `gbx.`, followed by the entity and the specific action in lowercase snake_case. For example, user authentication triggers must be formatted as `gbx.user.authenticated`. Payloads failing to use the mandatory `gbx.` prefix are rejected by the ingestion pipeline and generate a 422 Unprocessable Entity error response. Adherence to this convention is mandatory for all v1.0 data pipelines to guarantee accurate event mapping in billing and analytics reports.


## Escalation Contacts

The Globex platform team follows a defined three-tier escalation path for all v1.0 incidents within the Flowlytics platform. 

For Tier 1 issues, initial triage is handled directly by the Globex local support desk. If unresolved within two hours, the ticket escalates to Tier 2, assigned to the Globex internal systems engineers for infrastructure and data pipeline validation. Tier 3 is reserved for critical platform blocks requiring direct intervention from senior architects. 

All escalations must be logged through the designated ticketing portal using the standard severity classifications. Cross-team communication during a Tier 3 event requires opening a joint bridge within fifteen minutes of notification. Automated alerts for breached service-level agreements route directly to the on-call platform lead.
