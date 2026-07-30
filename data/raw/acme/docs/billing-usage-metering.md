---
slug: billing-usage-metering
title: Usage Metering
tenant: acme
product_area: billing
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# Usage Metering


## What Counts as a Billable Event

On the Usage Metering page, billable and free event types are distinguished to accurately calculate charges for customers. Billable events are those that incur costs, such as API requests, data storage, and messaging. These events are counted towards the customer's total usage and are reflected in their bill.

Free events, on the other hand, are not charged to customers, such as login attempts, dashboard views, and system notifications. These events are still recorded for auditing and analytics purposes but do not contribute to the customer's bill.

The following event types are considered billable:
- API requests
- Data storage usage
- Messaging (e.g., SMS, email)

The following event types are considered free:
- Login attempts
- Dashboard views
- System notifications
- Other non-chargeable events as defined by the platform.


## Metering Window

The Usage Metering page in Flowlytics billing v2.3 utilizes a UTC calendar month to accurately track and measure usage across all customers. This approach ensures that billing is consistent and aligned with the global standard for timekeeping.

A UTC calendar month is defined as the period from the first day of a month to the last day of the same month, regardless of the number of days in the month. This means that months with 31 days, such as January, March, May, July, August, October, and December, will have 31 days in the usage metering period, while months with fewer days, like February, will have 28 or 29 days depending on whether it's a leap year.

This calendar-based approach allows Flowlytics to provide accurate and reliable usage metrics, enabling customers to make informed decisions about their billing and resource allocation. The UTC calendar month is used consistently across all billing periods to ensure transparency and fairness in usage metering.


## Overage Charges

The overage rate for events exceeding the plan limit is calculated at a rate of $0.10 per 1,000 events. This rate applies to all events beyond the allocated limit specified in the current billing plan. The plan limit is the maximum number of events allowed within a given time period, and any events exceeding this limit are subject to the overage rate.

For example, if the plan limit is 10,000 events and the actual usage is 15,000 events, the overage would be 5,000 events (15,000 - 10,000). The overage rate of $0.10 per 1,000 events would be applied to this excess, resulting in an overage charge of $0.50 (5,000 events / 1,000 * $0.10). This charge will be reflected in the billing for the given time period. The overage rate remains the same for all plans and is a flat rate of $0.10 per 1,000 events.


| Plan | Included events | Overage per 1k |
|---|---|---|
| Starter | 100 | $0 |
| Growth | 1,000 | $499 |
| Enterprise | Unlimited | Custom |
