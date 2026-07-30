---
slug: billing-plans
title: Billing Plans
tenant: globex
product_area: billing
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Billing Plans


## Plan Comparison

The Billing Plans page in Flowlytics, version 2.2, offers three primary plans: Starter, Growth, and Enterprise. Each plan is designed to cater to the specific needs of different businesses.

- **Starter Plan**: This plan is ideal for small businesses or individuals who require basic analytics and billing capabilities. It supports up to 10,000 API requests per month, 1 user account, and 1 custom domain. The Starter Plan is priced at $99 per month.

- **Growth Plan**: Suitable for medium-sized businesses, the Growth Plan offers enhanced features and increased limits. It supports up to 50,000 API requests per month, 5 user accounts, and 3 custom domains. The Growth Plan is priced at $299 per month.

- **Enterprise Plan**: This plan is designed for large businesses and enterprises, offering advanced features, increased limits, and dedicated support. It supports up to 200,000 API requests per month, 20 user accounts, and 10 custom domains. The Enterprise Plan is priced at $999 per month.


| Plan | Monthly price | Events included | Seats |
|---|---|---|---|
| Starter | $0 | 100 | Standard |
| Growth | $499 | 1,000 | Extended |
| Enterprise | Custom | Unlimited | Custom |


## Plan Limits

When the event ceiling is reached, Flowlytics will prevent further events from being recorded for the billing plan. This is a safeguard to prevent excessive event volume from affecting performance and accuracy of analytics. Once the ceiling is hit, any subsequent events will be discarded and will not contribute to the plan's event count.

The event ceiling is enforced on a per-plan basis, allowing multiple plans to exceed their ceilings independently. For example, if a plan has an event ceiling of 10,000 and it reaches this limit, events will be discarded until the plan's event count is below the ceiling. The event ceiling does not affect billing, as charges are based on the actual number of events processed by Flowlytics. If you need to process a large volume of events, consider upgrading to a higher-tier plan or contacting Flowlytics support for assistance.


## Upgrading and Downgrading

When a billing plan change is made, the updated plan takes effect at the start of the next billing cycle. This means that any changes to the plan's pricing, features, or other settings will be applied to the next cycle's invoice. For example, if a customer is currently on a monthly billing cycle and is upgraded to a higher-tier plan on the 15th of the month, the new plan will take effect on the 1st of the next month.

It's worth noting that any changes made to a plan will not be retroactively applied to previous billing cycles. Customers will be charged according to the plan they were on at the time of each billing cycle.

In the event of a plan downgrade, the new plan will take effect immediately, and any overpayments will be credited back to the customer.
