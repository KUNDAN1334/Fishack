---
slug: billing-invoices
title: Invoices
tenant: globex
product_area: billing
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# Invoices


## Invoice Generation

Invoices are generated on the first day of each month. This process is automated and occurs at the beginning of every month. As a result, invoices for the preceding month are available for viewing and management on the first day of the current month.

The billing cycle is as follows:
- The system generates invoices for the preceding month on the first day of the current month.
- Invoices are then available for viewing, editing, and management on the Invoices page.
- This process ensures that invoices are always up-to-date and readily accessible for users to review and manage their billing information.

It is essential to note that this automated process does not require manual intervention, reducing the risk of errors and ensuring seamless billing operations.


## Proration

When a customer's plan is changed mid-cycle, the new pricing is applied immediately, and the difference in cost is prorated over the remaining days of the billing cycle. This ensures that the customer is only charged for the time they have used the new plan.

The proration is calculated on a daily basis, taking into account the number of days remaining in the billing cycle. To determine the daily proration amount, Flowlytics divides the difference in cost between the old and new plans by the number of days remaining in the cycle.

For example, if a customer's plan is changed from a $100 per month plan to a $120 per month plan on day 15 of a 30-day billing cycle, the daily proration amount would be calculated as follows:

- Calculate the difference in cost: $120 - $100 = $20
- Calculate the number of days remaining in the cycle: 30 - 15 = 15
- Calculate the daily proration amount: $20 / 15 = $1.33 per day

The customer would be charged the new plan price of $120 for the first 15 days of the cycle, and then an additional $20 (15 x $1.33) for the remaining days, resulting in a total charge of $140 for the cycle. This ensures that the customer is only charged for the time they have used the new plan, and that the proration is applied fairly and accurately.


## Invoice Delivery

On the 'Invoices' page, users can configure email recipients and download invoices as PDF documents. To specify email recipients, navigate to the 'Invoice Recipients' section and enter the desired email addresses. Multiple recipients can be separated by commas.

When an invoice is generated, Flowlytics will send a notification email to the specified recipients. The email will include a link to the invoice, which can be accessed directly from the email.

To download an invoice as a PDF document, click on the 'Download as PDF' button located next to the invoice number. The PDF document will be downloaded to the user's device, providing a permanent record of the invoice.

Note that the 'Download as PDF' feature is only available for invoices that have been generated in the current billing cycle.
