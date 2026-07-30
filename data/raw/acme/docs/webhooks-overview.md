---
slug: webhooks-overview
title: Webhooks Overview
tenant: acme
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Webhooks Overview


## Introduction

Flowlytics webhooks are a push-based event delivery mechanism that enables real-time notifications of key events within the platform. These events are delivered over HTTPS POST to a specified endpoint, allowing customers to integrate with external systems and automate workflows. 

Webhooks provide a scalable and efficient way to receive event notifications, reducing the need for frequent polling of the Flowlytics API. Key events that trigger webhooks include changes to customer data, billing updates, and system notifications. 

When a webhook event is triggered, Flowlytics sends a POST request to the configured endpoint with the event data in JSON format. The request includes a unique event ID and timestamp, allowing customers to track and verify the origin of the event. This enables customers to build custom integrations and automate processes in response to specific events, improving the overall efficiency and effectiveness of their workflow.


## Event Types

The Flowlytics platform emits the following event types via webhooks:

- **Subscription Created**: Triggered when a new subscription is created, including subscription ID, customer ID, and plan details.
- **Subscription Updated**: Triggered when an existing subscription is updated, including changes to plan details, billing cycle, or customer information.
- **Subscription Canceled**: Triggered when a subscription is canceled, including reason for cancellation and effective date.
- **Invoice Created**: Triggered when a new invoice is generated, including invoice ID, subscription ID, and billing details.
- **Payment Succeeded**: Triggered when a payment is successfully processed, including payment method, amount, and transaction details.
- **Payment Failed**: Triggered when a payment fails, including error code and transaction details.

These event types provide real-time notifications of key events within the platform, enabling seamless integration with external systems and workflows.


| Event | Trigger | Payload version |
|---|---|---|
| event.created | Standard | v2.2 |
| event.updated | Extended | v2.2 |
| invoice.paid | Custom | v2.2 |


## Delivery Guarantees

At-least-once delivery is a key aspect of Flowlytics' webhook system, ensuring that messages are processed even in the event of temporary failures. However, this means that ordering of messages is not guaranteed, and it's possible for duplicate messages to be received. To mitigate this, Flowlytics provides idempotency keys for each webhook event. 

Idempotency keys are unique identifiers that can be used to detect and discard duplicate messages. When a webhook event is received, the idempotency key is checked against a cache. If a matching key is found, the message is discarded, and no further action is taken. 

This approach ensures that even if a message is received multiple times, it will only be processed once. By using idempotency keys, developers can build robust and reliable webhook integrations with Flowlytics.


## Retry Logic

When sending requests to Flowlytics via webhooks, the platform employs an exponential backoff strategy to handle temporary failures. This strategy involves increasing the delay between retries after each failure. The initial delay is set to 30 seconds.

In the event of a request failure, the platform will automatically retry the request up to 3 times. This 3-attempt limit is explicitly enforced to prevent infinite loops and potential abuse. After the 3rd retry, the platform will consider the request failed and will not attempt further retries.

The exponential backoff delay is calculated based on the number of previous failures. The delay is doubled after each failure, up to a maximum of 4 minutes (30 seconds * 2^2). This strategy helps to prevent overwhelming the platform with repeated requests and ensures that the system remains stable and responsive. By implementing this strategy, Flowlytics ensures that webhooks are delivered efficiently and reliably.


### Backoff Schedule

The retry logic for webhooks in Flowlytics v2.2 is designed to ensure reliable delivery of notifications. When a webhook fails, the platform will attempt to resend the notification up to 3 times. The delay between each attempt increases exponentially. The first retry occurs after 1 minute, the second retry after 5 minutes, and the third retry after 15 minutes. This allows the receiving system sufficient time to recover from any issues that may have caused the initial failure, while also preventing repeated failures due to temporary network issues. By implementing this retry logic, Flowlytics ensures that webhooks are delivered successfully, even in the presence of minor connectivity issues.


### Dead Letter Queue

When retries exhaust, undeliverable events are routed to the Dead Letter Queue (DLQ). The DLQ serves as a holding area for events that cannot be successfully delivered to the intended recipient after a specified number of retry attempts. In Flowlytics, the default retry limit is 3 attempts, after which the event is moved to the DLQ.

The DLQ is designed to prevent event loss and provide a mechanism for further analysis or manual intervention. Administrators can access the DLQ to investigate issues, correct configuration errors, or re-queue events for further processing. By default, the DLQ is stored in the same database as the main event store, but this can be configured to use an external storage solution if required.
