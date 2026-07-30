---
slug: audit-logs
title: Audit Logs
tenant: acme
product_area: platform
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# Audit Logs


## What Is Logged

The Audit Logs page in Flowlytics v2.3 records security-relevant system actions to support compliance and investigation workflows. This view captures three primary event categories: authentication, configuration, and data-access events. 

Authentication events document all login attempts, including successful sign-ins, multi-factor authentication challenges, and failed credential submissions across all tenant users. Configuration events track modifications made to platform settings, webhook endpoints, billing thresholds, and team permission roles. Data-access events log queries executed against sensitive analytics exports and customer records, recording the specific user ID, timestamp, and target resource. 

Administrators can filter these records by event category, severity level, or date range directly within the dashboard. All captured entries are retained in accordance with enterprise data governance policies and cannot be manually altered or deleted by platform users.


## Retention Period

The Audit Logs page in Flowlytics platform version 2.3 provides a comprehensive, chronological record of all security-relevant actions, administrative modifications, and data access events executed across your organization. System administrators can utilize these logs to investigate security incidents, review permission changes, and maintain compliance with internal governance policies. 

In accordance with platform data retention policies, all generated audit logs are securely stored and retained for a mandatory period of 90 days. Once this 90-day window elapses, older log entries are permanently purged from the system automatically. Organizations requiring long-term archiving beyond this 90-day limit must export their audit records prior to the expiration date using the available data export tools within the platform.


## Exporting Audit Logs

The Audit Logs page in Flowlytics v2.3 provides users with the ability to view and manage API and scheduled export options. 

Users can access the API settings by clicking on the 'API' tab within the Audit Logs page. Here, they can view and manage API keys, including creating new keys, revoking existing keys, and viewing key usage. 

Scheduled exports allow users to automate the export of audit logs to a designated storage location, such as Amazon S3 or Google Cloud Storage. Users can configure export schedules, including frequency, start date, and end date, as well as specify the format and storage location for the exported logs. 

Available export formats include CSV and JSON. Users can also specify a maximum log size of 100 MB per export file.
