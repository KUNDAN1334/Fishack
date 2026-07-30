---
slug: acme-custom-sla
title: Acme Service Level Agreement
tenant: acme
product_area: platform
doc_version: v1.2
effective_date: 2026-03-20
source_type: docs
---


# Acme Service Level Agreement


## Uptime Commitment

Flowlytics guarantees a 99.95% uptime commitment specific to Acme for the platform, version 1.2. This availability metric is calculated monthly, excluding scheduled maintenance windows that have been communicated to Acme at least forty-eight hours in advance. 

If the platform fails to meet the 99.95% uptime commitment during any given calendar month, Acme becomes eligible for service credits as outlined in the primary agreement. To claim a credit, Acme must submit a support ticket within thirty days of the end of the affected month. Flowlytics monitoring systems are the sole source of truth for measuring uptime performance and determining eligibility. Unplanned outages resulting from third-party integrations or issues originating from Acme's own infrastructure are excluded from the uptime calculation.


## Support Response Times

Under the Acme Service Level Agreement on platform v1.2, incident management for critical disruptions requires immediate escalation and triage. For any designated Acme P1 incident, the Flowlytics support team guarantees a formal response within 30 minutes of initial ticket creation. 

This response timeframe applies exclusively to issues classified as P1 under the Acme Service Level Agreement framework. The 30-minute clock starts immediately when an alert triggers through the monitoring system or when a priority ticket is manually submitted via the primary support portal. Subsequent updates and remediation progress follow the standard operational cadence defined elsewhere in the platform v1.2 documentation. Failure to meet the 30-minute threshold for an Acme P1 event logs a service credit exception against the monthly billing cycle.


| Severity | Response | Resolution target |
|---|---|---|
| P1 | Standard | Standard |
| P2 | Extended | Extended |
| P3 | Custom | Custom |


## Service Credits

Flowlytics version 1.2 calculates service level agreement credits based on the monthly uptime percentage of the Acme Service Level Agreement. If monthly uptime falls below 99.9%, customers are eligible for a service credit applied to subsequent billing cycles. For uptime between 99.0% and 99.8%, the credit issued is 10% of the monthly subscription fee. For uptime between 95.0% and 98.9%, the credit increases to 25% of the monthly fee. If uptime drops below 95.0%, customers receive a 50% credit. To receive a credit, account administrators must submit a formal request through the Flowlytics support portal within 30 days of the end of the affected billing month. Credits are non-refundable, cannot be exchanged for cash, and apply exclusively to future platform usage fees.
