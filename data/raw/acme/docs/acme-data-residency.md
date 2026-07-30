---
slug: acme-data-residency
title: Acme Data Residency
tenant: acme
product_area: platform
doc_version: v1.1
effective_date: 2026-03-01
source_type: docs
---


# Acme Data Residency


## EU Region Pinning

Flowlytics version 1.1 includes the Acme Data Residency configuration, which ensures all customer data originating from Acme is permanently pinned to the eu-central region. When this residency setting is active, event ingestion, processing pipelines, billing records, and long-term storage buckets are strictly isolated within the eu-central infrastructure. 

Data traffic originating from Acme will not replicate or transfer across regional boundaries, satisfying compliance mandates and geographic residency requirements. Platform administrators can verify region pinning status at any time through the compliance dashboard. If an attempted write operation or data transfer originates outside the designated region while the pinning rule is enforced, the platform rejects the payload. Ensure all client-side SDKs and ingestion endpoints are correctly pointed to the regional endpoints designated for eu-central to prevent routing errors during data synchronization.


## Cross-Region Restrictions

When configuring data residency within version 1.1 of the platform on the Acme Data Residency page, certain operational components and associated metadata cannot leave your designated geographic region under any circumstances. Specifically, raw event payloads ingested from your client applications, customer Personally Identifiable Information stored within user profiles, and active database replicas housing your tenant-specific billing logs remain strictly bound to your selected jurisdiction. Furthermore, encryption keys managed through regional Key Management Service instances and real-time data pipeline buffers cannot be transferred or mirrored across international boundaries. Compliance auditing logs generated during routine synchronization tasks are also subject to this regional containment policy to satisfy strict local data protection regulations and platform security standards.
