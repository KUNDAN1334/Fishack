---
slug: api-rate-limits
title: API Rate Limits
tenant: acme
product_area: platform
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# API Rate Limits


## Default Limits

The per-plan request ceilings are as follows:

- Free plan: 100 requests per minute
- Starter plan: 500 requests per minute
- Growth plan: 1,000 requests per minute
- Pro plan: 5,000 requests per minute
- Enterprise plan: custom rate limits, please contact support for more information

Note that these ceilings apply to all API requests made to the Flowlytics platform, including but not limited to data ingestion, query execution, and billing information retrieval. Exceeding these ceilings may result in rate limit errors, which can be identified by the error code '429 Too Many Requests'. If you are experiencing issues with rate limits, please refer to our documentation on rate limit management and consider upgrading to a plan with higher ceilings.


| Plan | Requests/min | Burst |
|---|---|---|
| Starter | 100 | Standard |
| Growth | 1,000 | Extended |
| Enterprise | Unlimited | Custom |


## Rate Limit Headers

The API Rate Limits page displays the current rate limits for your Flowlytics account. These limits are enforced to prevent abuse and ensure fair usage of the platform's resources. The rate limits are represented by three HTTP headers: X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset.

X-RateLimit-Limit specifies the total number of API requests allowed per hour, which is 1000 for the v2.1 platform. X-RateLimit-Remaining indicates the number of requests remaining within the current hour, while X-RateLimit-Reset provides the timestamp in seconds when the rate limit will reset. This allows you to plan your API requests accordingly and avoid hitting the rate limit. If you exceed the rate limit, you will receive a 429 Too Many Requests error response. Monitoring these headers helps you optimize your API usage and prevent rate limit-related issues.


## Handling 429 Responses

When the API rate limits are exceeded, Flowlytics returns the ERR_RATE_LIMITED error code. This indicates that the request has been temporarily blocked to prevent abuse and ensure fair usage of the platform.

To handle this error, we recommend implementing exponential backoff, a strategy that increases the time between retries after each failure. This approach helps to prevent overwhelming the API with repeated requests and reduces the likelihood of further rate limit errors.

The recommended backoff strategy is to wait for 1 second after the first failure, 2 seconds after the second failure, 4 seconds after the third failure, and so on, doubling the wait time after each failure. This pattern continues until the request is successful or a maximum of 10 attempts have been made. By implementing exponential backoff, you can effectively manage API rate limits and ensure a stable experience for your application.
