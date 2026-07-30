---
slug: data-sync-latency
title: Data Sync and Latency
tenant: globex
product_area: analytics
doc_version: v2.0
effective_date: 2026-01-15
source_type: docs
---


# Data Sync and Latency


## Ingestion Pipeline Stages

When an event is received by the Flowlytics API, it is first validated to ensure it conforms to the expected format and structure. If valid, the event is then processed and stored in a temporary buffer. From the buffer, the event is written to a message queue, where it is consumed by a worker process. This worker process is responsible for transforming the event into a format suitable for storage in the queryable database.

The transformed event is then inserted into the database, where it is indexed and made available for querying. The entire process, from API receipt to queryable storage, typically takes less than 5 milliseconds. This is due in part to the use of a distributed architecture, which allows multiple worker processes to handle the event processing concurrently. As a result, events are typically available for querying within 1-2 milliseconds of being received by the API.


## Expected Latency

The Data Sync and Latency page provides a detailed overview of the data synchronization process and latency within the analytics platform. This page is essential for understanding how data is aggregated and made available for analysis.

Data is synced from connected accounts to the Flowlytics platform every 5 minutes. However, events may take up to 15 minutes to appear in dashboards due to processing and caching mechanisms. This latency is a standard aspect of the platform and does not impact the accuracy of the data.

It's worth noting that data latency can vary depending on the volume of data being processed and the load on the system. In general, high-volume data sets may experience slightly longer latency times. However, this is typically within the 15-minute window.


## Synchronization Delays

Delayed data can occur due to several common causes. One reason is when the data ingestion rate exceeds the processing capacity of the Flowlytics system, resulting in a backlog of unprocessed data. This can be mitigated by adjusting the data ingestion rate or upgrading to a higher-tier plan.

Another cause is when data is not properly formatted, causing the system to reject it. This can lead to a delay in data processing and subsequent delays in analytics and billing. Ensuring that data is correctly formatted and meets the required schema is essential.

Backfill behavior can also contribute to delayed data. When a new data source is added or an existing one is updated, Flowlytics performs a backfill to ensure complete data coverage. This process can take up to 24 hours to complete, depending on the size of the data set and the system load.


## Monitoring Sync Health

The pipeline health page provides a visual representation of the data sync process, indicating the status of each pipeline. The pipeline health status is categorized into three main colors: green, yellow, and red. A green status indicates that the pipeline is healthy and data is being synced successfully. A yellow status signifies a warning, where the pipeline is experiencing minor issues, such as delayed data processing or connectivity problems. A red status denotes a critical error, where the pipeline has failed to sync data and requires immediate attention.

Some common pipeline health statuses include:
- 'Syncing' (green): data is being synced in real-time.
- 'Delayed' (yellow): data processing is taking longer than expected.
- 'Error' (red): data sync has failed due to a critical issue.
- 'Unknown' (gray): the pipeline status is unknown or not available.
