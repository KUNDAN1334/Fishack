---
slug: segments-and-cohorts
title: Segments and Cohorts
tenant: acme
product_area: analytics
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# Segments and Cohorts


## Building a Segment

The filter builder on the 'Segments and Cohorts' page in Flowlytics analytics v2.1 allows users to create complex queries by combining multiple conditions using boolean logic. The filter builder consists of a series of panels, each representing a condition that can be added to the query.

Conditions can be combined using the following operators: AND, OR, and NOT. The AND operator requires all conditions to be true, while the OR operator requires at least one condition to be true. The NOT operator negates the condition that follows it.

Users can add up to 5 conditions to the filter builder. Each condition can be further refined by selecting specific fields, operators, and values. The filter builder also supports the use of parentheses to group conditions and change the order of operations. By combining multiple conditions using boolean logic, users can create sophisticated queries that meet their specific needs.


## Cohort Retention Analysis

Retention grids on the 'Segments and Cohorts' page (analytics, v2.1) are computed using a combination of user interaction data and time-based calculations. For each segment or cohort, the platform aggregates user data from the selected time range, which defaults to the last 30 days. The retention grid displays the percentage of users who remained active at each interval, up to a maximum of 30 days.

The platform uses a 0-100% scale to represent user retention, with 100% indicating that all users remained active throughout the selected time range. The grid is divided into 30 equal intervals, with each interval representing a 1-day period. The platform calculates retention for each interval by comparing the number of active users at the start of the interval to the number of active users at the end of the interval. This calculation is performed for each segment or cohort, resulting in a unique retention grid for each.


## Segment Refresh Cadence

The 'Segments and Cohorts' page in analytics v2.1 provides real-time insights into customer behavior and preferences. Segments are dynamic groups of customers that are re-evaluated every hour to ensure up-to-date analysis. This hourly recompute allows for timely detection of changes in customer behavior and preferences, enabling data-driven decisions.

The recompute process occurs at the top of each hour, updating segment membership and metrics accordingly. This ensures that segment data remains accurate and relevant, even as customer behavior and preferences shift. As a result, users can rely on the 'Segments and Cohorts' page to provide a current snapshot of their customer base.

Key benefits of hourly segment recompute include reduced latency in data analysis and improved decision-making. Users can respond quickly to changes in customer behavior, optimizing marketing campaigns and product offerings to meet evolving customer needs.
