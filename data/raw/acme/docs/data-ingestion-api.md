---
slug: data-ingestion-api
title: Data Ingestion API
tenant: acme
product_area: analytics
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# Data Ingestion API


## Sending Events

To send events to Flowlytics, use the POST /v2/events endpoint. This endpoint supports both single and batch modes.

In single mode, send a single event in the request body. The event object must contain the required fields: `event_id`, `timestamp`, `customer_id`, and `event_type`. The `event_id` must be a unique identifier for the event, and `timestamp` must be in ISO 8601 format.

In batch mode, send a JSON array of events in the request body. Each event object must contain the required fields. The `events` parameter is optional and can be used to specify the maximum number of events to process in a single request. The default limit is 1000 events. If the limit is exceeded, a `429 Too Many Requests` error is returned.


## Batch Limits

When sending data to Flowlytics using the Data Ingestion API, it is essential to adhere to the batch request and payload size limits. Each batch request can contain a maximum of 500 events. This limit is in place to prevent overwhelming the system and ensure timely processing of your data.

In addition to the event limit, the total payload size of each batch request is capped at 5 MB. This includes all data sent in the request body, including event data, headers, and any other metadata. Exceeding this limit will result in a failed request. To avoid this, consider breaking up large datasets into smaller batches or optimizing your data to reduce its overall size. By respecting these limits, you can ensure smooth and efficient data ingestion into Flowlytics.


## Schema Validation

When a property type changes, the Data Ingestion API may return an ERR_SCHEMA_MISMATCH error. This occurs when the client attempts to update a property with a new type that does not match the expected schema. The expected schema is based on the property's current type and any previous updates.

To resolve this issue, ensure that the new property type matches the expected schema. If the property type has changed, update the schema accordingly. The Data Ingestion API expects the new property type to be a compatible upgrade, such as updating a string property to a longer string type.

Common examples of compatible upgrades include:
- Updating a string property to a longer string type (e.g., from string to string(255))
- Updating a numeric property to a larger numeric type (e.g., from integer to long)
Avoid downgrading property types, as this may cause data loss or corruption. If you are unsure about the expected schema, consult the Data Ingestion API documentation or contact Flowlytics support.


## Idempotency

The deduplication window for events in the Data Ingestion API is based on the event_id field. When processing events, Flowlytics will automatically remove duplicate events with the same event_id within a 1-hour window. This means that if two events with the same event_id are received within 1 hour of each other, only the first event will be processed and the second event will be discarded.

This deduplication window is designed to prevent duplicate events from skewing analytics and billing data. By default, the deduplication window is set to 1 hour, but this can be adjusted by contacting Flowlytics support for custom configurations. Note that events with different event_id values will not be affected by this deduplication process.
