---
slug: data-export
title: Data Export
tenant: globex
product_area: analytics
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Data Export


## Export Formats

The Data Export page in Flowlytics analytics v2.2 allows users to export data in three formats: CSV, JSON, and Parquet. CSV (Comma Separated Values) is a widely supported format for exporting data, suitable for most use cases. JSON (JavaScript Object Notation) is a lightweight format ideal for importing data into other applications or services. Parquet is a columnar storage format optimized for large-scale data analysis.

Users can select the desired export format and configure the export settings. The available options include choosing the data range and selecting specific data fields to export. The export process can be triggered manually or scheduled to run at regular intervals. In the event of an error, the export process will be halted and an error message will be displayed. Error codes will be provided to assist with troubleshooting.


| Format | Max rows | Compression |
|---|---|---|
| CSV | 100 | Standard |
| JSON | 1,000 | Extended |
| Parquet | Unlimited | Custom |


## Scheduled Exports

The Data Export page in analytics v2.2 allows users to schedule exports of their data to Amazon S3 or Google Cloud Storage (GCS) using cron-style scheduling. To set up a scheduled export, navigate to the Data Export page, select the desired data source and frequency, and choose the storage destination.

The cron-style scheduling syntax is used to specify the export schedule. The format is in the style of cron, with five fields separated by spaces: minute, hour, day of month, month, and day of week. For example, "0 0 * * * *" would export data every day at midnight. The minimum schedule interval is 1 minute, and the maximum is 59 minutes. Users can also specify a specific date range for the export.

Note that the cron syntax is case-sensitive and must be entered exactly as shown.


## Export Retention

The Data Export page in analytics v2.2 allows users to export their data in various formats. Once exported, these files are retained in the system for a limited period. According to our retention policy, exported files are kept for 7 days from the date of export. After this period, they are automatically deleted from our servers. This means that users should ensure they download their exported files promptly to avoid losing access to their data. It's also essential to note that this retention period may be subject to change, and users will be notified of any updates. For security and compliance reasons, we do not provide any additional storage or backup options for exported files. Users should plan accordingly to ensure they have a secure backup of their data.
