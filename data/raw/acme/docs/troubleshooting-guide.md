---
slug: troubleshooting-guide
title: Troubleshooting Guide
tenant: acme
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Troubleshooting Guide


## Data Not Appearing

When events fail to appear in your Flowlytics dashboard for platform version v2.2, complete the following verification checklist before contacting support. First, confirm that your tracking snippet is properly initialized and firing on the target pages. Second, check your network tab for blocked requests or CORS policy errors that prevent data transmission. Third, verify that your API key matches the current environment and has not been revoked. Fourth, ensure your payload does not exceed the maximum size limit of 1MB per request. Finally, check whether your account has hit any rate limits. If events still do not register after completing this checklist, reference error code ERR-409 when submitting a ticket to the support team for expedited assistance.


## Authentication Failures

The ERR_INVALID_KEY error code in Flowlytics platform v2.2 indicates that the API key provided in the authorization header is not recognized or has been rejected. This failure typically stems from one of three specific causes. First, the API key may have been revoked or deleted within the security settings dashboard. Second, the string may contain typographical errors, trailing whitespace, or missing characters copied during transfer. Third, requests may be using an API key generated for a different environment, such as passing a development key to the production endpoint or vice versa. Verify the key string against your current environment credentials and ensure the token remains active in your account configuration. If the key has been compromised or expired, generate a new credential pair immediately to restore access.


## Slow Dashboards

To diagnose slow dashboard loads in Flowlytics v2.2, first check the browser network tab to isolate whether latency stems from network transit or client-side rendering. Large datasets exceeding the recommended limit of 50,000 active query rows per view commonly cause browser-side rendering degradation. If you observe HTTP 504 gateway timeout errors during initial load, the underlying data warehouse query has exceeded the default execution timeout threshold of 30 seconds. Optimize your aggregation queries by applying restrictive date range filters or reducing the number of concurrent custom metrics displayed simultaneously on a single dashboard canvas. Ensure that your organization has not surpassed the active user concurrent connection limit specified in your current billing tier, as queue contention directly impacts response latency. If performance issues persist after applying these optimizations, capture the request ID from the response header and contact support with the exact timestamp of the occurrence.


## Getting Support

To reach the Flowlytics support team for platform version v2.2 assistance, submit a request through the in-app help widget or email support directly. When contacting support, you must include your organization ID, the exact text of any error code received, and a detailed reproduction of the issue. Omitting these details may delay the resolution time. For urgent billing or critical analytics pipeline failures, mark your ticket with high priority. Our team reviews all submissions in the order they are received, and you will get an automated confirmation containing your tracking number once your message is successfully logged in our system.
