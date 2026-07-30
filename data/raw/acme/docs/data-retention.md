---
slug: data-retention
title: Data Retention
tenant: acme
product_area: platform
doc_version: v2.0
effective_date: 2026-01-15
source_type: docs
---


# Data Retention


## Retention by Plan

The Flowlytics platform v2.0 Data Retention page outlines how long your organization's telemetry and transaction records remain accessible within the system. Under the Growth plan, raw event data is retained for 12 months from the exact date of ingestion. 

Once this 12-month window elapses, raw event records are permanently purged from the active database in accordance with our automated lifecycle policies. If your business requires extended historical analysis beyond this timeframe, you must export your telemetry via our API or upgrade to a higher-tier enterprise agreement before the retention threshold is reached. Historical aggregated metrics and monthly billing summaries remain accessible independently of the raw event retention period, subject to your active subscription status.


| Plan | Raw events | Aggregates |
|---|---|---|
| Starter | 100 | Standard |
| Growth | 1,000 | Extended |
| Enterprise | Unlimited | Custom |


## Deletion Requests

Flowlytics platform v2.0 handles GDPR deletion requests through the Data Retention management interface. When a data subject invokes their right to erasure, administrators can initiate a permanent deletion workflow. This process purges all identifiable telemetry, usage records, and billing metadata associated with the specified user ID across primary and replica databases. 

Administrators must verify the request identifier before submission. Once initiated, the deletion job runs asynchronously and completes within a 72-hour compliance window. An automated audit log entry is generated upon successful completion, recording the request ID, timestamp, and executing administrator. Data purged during this workflow cannot be recovered. Backups retained for disaster recovery age out naturally according to the standard retention schedule, but are cryptographically inaccessible immediately upon workflow execution.


## Archival Storage

Flowlytics platform version 2.0 introduces automated cold storage for all historical records exceeding the active 90-day retention window. Data aged beyond 90 days is automatically migrated to low-cost archival storage to optimize primary database performance and reduce infrastructure overhead. 

While in cold storage, records remain fully accessible through the Flowlytics query engine, though retrieval operations incur a latency increase of up to 120 seconds compared to active tier queries. Administrators can configure custom transition thresholds or exempt specific event categories from archival by navigating to the retention policy settings. Restoring archived datasets to the primary tier requires manual initiation and completes within 24 hours. Export jobs referencing data in cold storage will automatically queue and execute once retrieval is confirmed by the system.
