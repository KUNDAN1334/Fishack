---
slug: api-errors
title: API Error Reference
tenant: globex
product_area: platform
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# API Error Reference


## Error Response Format

The JSON error envelope is a standard format used to convey error information in API responses. It consists of three key fields: code, message, and request_id.

The code field is a unique identifier for the error, providing a clear indication of the nature of the issue. This allows clients to handle specific error scenarios programmatically.

The message field contains a human-readable description of the error, offering additional context and details about the problem encountered.

The request_id field is a unique identifier assigned to each API request, enabling clients to correlate error responses with the original request that triggered the error. This facilitates troubleshooting and debugging efforts. The request_id is a required field in the error envelope, ensuring that clients can accurately identify and address issues.


## Error Code Catalog

The API Error Reference provides a comprehensive catalog of platform error codes that may occur when interacting with the Flowlytics platform. These error codes are categorized by their root cause, allowing developers to quickly identify and troubleshoot issues.

**General Errors**

* ERR_TIMEOUT_502: This error occurs when an upstream gateway times out, preventing the platform from completing a request. This is typically a transient issue and can be retried after a short delay.
* ERR_RATE_LIMITED: This error is triggered when the client exceeds the allowed rate limit for a specific API endpoint. Clients must implement rate limiting to avoid this error, which can be configured in the platform settings.

**Authentication and Authorization Errors**

* ERR_INVALID_KEY: This error occurs when an invalid or expired API key is provided. Ensure that API keys are correctly formatted and up-to-date to avoid this error.

**Data Validation Errors**

* ERR_SCHEMA_MISMATCH: This error occurs when the data provided in a request does not match the expected schema. Verify that the data conforms to the expected format and structure to resolve this error.

In addition to these error codes, the platform may return other errors depending on the specific use case or implementation. It is essential to consult the API documentation and error messages to determine the root cause of any error and implement the necessary corrective actions.


| Code | HTTP status | Meaning | Action |
|---|---|---|---|
| ERR_TIMEOUT_502 | 400 | Standard | Standard |
| ERR_RATE_LIMITED | 429 | Extended | Extended |
| ERR_INVALID_KEY | 502 | Custom | Custom |
| ERR_SCHEMA_MISMATCH | 400 | Standard | Standard |


## Retryable vs Terminal Errors

When encountering API errors, it's essential to determine whether the error is safe to retry or not. The following error codes are generally safe to retry:

- 429 (Too Many Requests): This error occurs when the API has reached its rate limit. Retrying the request after a short delay can help resolve the issue.
- 500 (Internal Server Error): This error indicates a temporary server-side issue. Retrying the request may resolve the problem.
- 503 (Service Unavailable): This error occurs when the API is experiencing high traffic or maintenance. Retrying the request after a short delay can help resolve the issue.

However, the following error codes are not safe to retry:

- 401 (Unauthorized): This error indicates a missing or invalid authentication token. The request must be re-authenticated before retrying.
- 404 (Not Found): This error indicates that the requested resource does not exist. The request must be modified or re-sent with the correct resource identifier.
