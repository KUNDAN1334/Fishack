---
slug: billing-payment-methods
title: Payment Methods
tenant: globex
product_area: billing
doc_version: v2.0
effective_date: 2026-01-15
source_type: docs
---


# Payment Methods


## Supported Methods

The Flowlytics v2.0 billing platform supports multiple payment methods tailored to different account tiers. For standard and growth accounts, credit card processing is available for all major providers, supporting automated monthly renewals and immediate invoice clearance. 

ACH transfers are supported for United States-based accounts operating on business tiers, typically processing within three to five business days. For Enterprise tier subscribers, wire transfers are fully supported as a designated payment method. Enterprise customers opting for wire transfers must coordinate directly with their assigned account manager to retrieve banking instructions and ensure timely posting to avoid service interruptions. All payment methods can be managed, updated, or audited from the primary dashboard under billing settings.


## Failed Payments

When a transaction fails with error code ERR_PAYMENT_DECLINED, the Flowlytics billing v2.0 system initiates the automated dunning schedule to recover the failed invoice without immediate service interruption. 

The standard retry attempts follow a strict schedule. The platform makes the first automated retry 24 hours after the initial failure. If the second attempt also results in ERR_PAYMENT_DECLINED, a third and final retry is executed 72 hours after the second attempt. 

Throughout this dunning schedule, administrators receive email notifications on each retry day. If all retry attempts are exhausted without a successful charge, the account transitions to a restricted state, and billing v2.0 flags the subscription as past_due until a valid payment method is updated in the dashboard.


## Updating a Card

The self-serve card update flow in billing v2.0 allows enterprise tenants to update their primary payment methods without contacting Flowlytics support. Navigate to the Payment Methods page and select Edit on the target card to modify expiration dates, billing addresses, or replace the card entirely. All updates require 3D Secure verification when mandated by regional banking regulations. 

When a card update fails, the system returns specific error codes to diagnose the issue immediately. Error code `ERR_CARD_EXPIRED` indicates the expiration date has passed, `ERR_INSUFFICIENT_FUNDS` signals a declined pre-authorization charge, and `ERR_GATEWAY_TIMEOUT` points to an upstream processor failure. Tenants must resolve these errors before Flowlytics can process subsequent subscription renewals or usage-based billing charges.
