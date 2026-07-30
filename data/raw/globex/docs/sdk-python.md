---
slug: sdk-python
title: Python SDK
tenant: globex
product_area: platform
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# Python SDK


## Installation

To integrate Flowlytics platform version 2.1 into your Python applications, install the official package using pip. Open your terminal and run pip install flowlytics. This command downloads and installs the package along with all required dependencies into your active Python environment. Ensure you are using Python 3.8 or higher for full compatibility with the SDK. After installation, verify that the package is correctly registered by running pip show flowlytics. You can then import the client into your project files and initialize it using your project API keys as detailed in the subsequent configuration guide.


## Client Configuration

The Flowlytics Python SDK v2.1 includes configurable parameters for handling network timeouts, event batching, and automatic retries to ensure reliable telemetry delivery. 

By default, the SDK sets a connection timeout of 5 seconds and a read timeout of 10 seconds. You can override these thresholds during client initialization based on your infrastructure latency requirements.

Events are buffered locally in memory and dispatched in automatic batches to optimize network utilization. The default batch size is 100 events, with a flush interval of 2 seconds. When the buffer reaches capacity or the timer expires, a transmission is triggered.

If an API request fails due to transient network errors or rate limits, the SDK executes automatic retries using an exponential backoff strategy, performing up to 3 retry attempts before discarding the payload and logging an error.


## Async Usage

The Flowlytics Python SDK v2.1 includes an asynchronous client designed for high-throughput, non-blocking telemetry ingestion in modern event-driven architectures. The `AsyncFlowlyticsClient` manages an in-memory event queue and background dispatch workers to prevent blocking the main event loop during high-volume operations. 

When configuring the asynchronous client, you can manage buffer capacities and flush thresholds using explicit configuration parameters. The client triggers an automatic batch dispatch whenever the internal buffer reaches 500 events or every 10 seconds, whichever occurs first. 

To prevent data loss during application shutdown or service termination, you must explicitly call the `await client.flush()` method before exiting your application context. This ensures all remaining queued payloads in the memory buffer are fully transmitted to the Flowlytics ingestion pipeline prior to process teardown.
