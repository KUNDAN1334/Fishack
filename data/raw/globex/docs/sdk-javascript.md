---
slug: sdk-javascript
title: JavaScript SDK
tenant: globex
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# JavaScript SDK


## Installation

To integrate the Flowlytics platform using version v2.2 of the JavaScript SDK, you can install the package via npm or include the library directly through a script tag. 

For modern frontend projects, install the package by running `npm install @flowlytics/browser-sdk`. This method supports module bundlers and TypeScript out of the box. 

Alternatively, for lightweight deployments or legacy environments, load the SDK asynchronously via a script tag in your HTML document's header. Ensure you append your project write key to the initialization parameters regardless of the installation method chosen. Both integration paths automatically track standard page views and session metadata without requiring custom event instrumentation. Refer to the configuration reference for advanced environment flags and initialization options available in v2.2.


## Initialization

To initialize the Flowlytics JavaScript SDK on your platform, you must supply your project write key and configure the required initialization parameters. The write key authenticates your client-side requests and routes inbound event streams to your specific organization workspace. 

When calling the initialization method in v2.2, pass an options object containing your write key alongside optional configuration properties. The SDK supports setting a custom API host URL, enabling debug mode for local troubleshooting, and configuring automatic page view tracking. Ensure that your write key is kept secure and that you only initialize the SDK once per application lifecycle to prevent duplicate event emission. Failing to provide a valid write key during initialization will result in authentication error SDK_ERR_401 and halt all outgoing telemetry data streams.


## Tracking Events

The Flowlytics JavaScript SDK v2.2 provides core tracking and identification methods for client-side implementations. Use the `track` method to record user actions and custom events within your web application. The function accepts an event name string and an optional properties object containing up to 50 key-value pairs. 

Use the `identify` method to associate a user session with a specific profile ID and persistent traits. This method requires a unique distinct_id string and accepts a traits dictionary to store metadata such as subscription tier or company affiliation. 

Use the `page` method to record page views and virtual route transitions in single-page applications. This method automatically captures the current URL, referrer, and document title, while accepting custom properties to override default parameters or append context. 

For implementation reference, the `track` method is invoked as `flowlytics.track('Button Clicked', { plan: 'enterprise' })`. The `identify` method is called using `flowlytics.identify('usr_9921b', { role: 'admin' })`. The `page` method executes via `flowlytics.page('Dashboard', { section: 'analytics' })`. Ensure your project initialization completes successfully before calling these asynchronous methods to prevent dropped events or unhandled exception errors.
