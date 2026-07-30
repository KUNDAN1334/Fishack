---
slug: custom-metrics
title: Custom Metrics
tenant: globex
product_area: analytics
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Custom Metrics


## Defining a Metric

On the Custom Metrics page, the metric builder allows users to create and configure custom metrics for their Flowlytics analytics. The aggregation types determine how the data is processed and displayed. The available aggregation types include Sum, Average, Count, and Standard Deviation. 

Sum aggregates the total value of the data, while Average calculates the mean value. Count returns the number of data points, and Standard Deviation measures the dispersion of the data. 

Users can select the aggregation type based on their specific needs, such as calculating total revenue or average response time. The chosen aggregation type will be applied to the selected data source, providing a customized view of the analytics data. This flexibility enables users to create tailored metrics that meet their business requirements.


## Formula Syntax

The Custom Metrics page in Flowlytics analytics v2.2 allows users to create custom metrics using a variety of supported operators and functions. These operators and functions enable users to perform complex calculations and transformations on their data.

The following operators are supported:

- Arithmetic operators: +, -, \*, /, %
- Comparison operators: ==, !=, <, >, <=, >=
- Logical operators: AND, OR, NOT
- String operators: CONCAT, CONTAINS, STARTS_WITH, ENDS_WITH

The following functions are also supported:

- Math functions: ABS, CEIL, FLOOR, ROUND
- String functions: LENGTH, LOWER, UPPER, TRIM
- Date and time functions: NOW, TODAY, TOMORROW, YESTERDAY
- Conditional functions: IF, IIF, SWITCH

Users can combine these operators and functions to create complex custom metrics. For example, a user can calculate the average revenue per user (ARPU) by using the AVG function on the revenue column and dividing it by the count of users.

When using custom metrics, users can also apply filters and group by clauses to further refine their results. The Custom Metrics page provides a visual interface for creating and editing custom metrics, making it easy for users to create and manage their custom metrics.

By supporting a wide range of operators and functions, the Custom Metrics page in Flowlytics analytics v2.2 provides users with the flexibility and power to create complex custom metrics that meet their specific needs.


## Metric Limits

On the Custom Metrics page in analytics v2.2, users on the Growth plan have access to a maximum of 50 custom metrics per workspace. This allows administrators to track and visualize specific data points relevant to their business, such as revenue, user engagement, or product adoption.

Custom metrics can be created and managed by users with the necessary permissions. Each custom metric can be configured to display data from various sources, including but not limited to, user behavior, transactional data, and system logs. The data is then visualized in a user-friendly format, enabling data-driven decision making.

The 50 custom metric limit is in place to strike a balance between flexibility and manageability. It enables users to track a sufficient number of key performance indicators (KPIs) without overwhelming the analytics platform or creating unnecessary complexity. Users can always reach out to support for assistance with custom metric management or to discuss potential upgrades to higher plans with increased metric limits.
