---
slug: query-engine
title: Query Engine
tenant: acme
product_area: analytics
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# Query Engine


## Query Language Basics

The Flowlytics query syntax is used to extract and manipulate data from the analytics database. It consists of a combination of keywords, operators, and functions that are used to construct a query.

A query is composed of a `SELECT` statement followed by a `FROM` clause, which specifies the data source. The `SELECT` statement can include one or more columns, which can be aggregated using functions such as `SUM`, `AVG`, and `COUNT`. The `FROM` clause can specify one or more data sources, which can be joined using the `JOIN` operator.

The query syntax also supports filtering data using the `WHERE` clause, which can include conditions such as equality, inequality, and range checks. Additionally, the `GROUP BY` clause can be used to group data by one or more columns, and the `HAVING` clause can be used to filter groups based on aggregated values.


## Query Timeouts

The Query Engine page in analytics v2.3 has a timeout limit of 30 seconds for queries. If a query exceeds this time limit, it will be terminated and return an error code of ERR_TIMEOUT_502. This timeout is in place to prevent long-running queries from impacting system performance and causing delays for other users.

Queries that are expected to take longer than 30 seconds should be optimized or split into smaller, more manageable parts. This may involve rephrasing the query, reducing the amount of data being processed, or using more efficient algorithms.

If you encounter the ERR_TIMEOUT_502 error, review your query to determine the cause of the timeout and make necessary adjustments to prevent it from occurring in the future. You can also consider increasing the timeout limit, but this should be done with caution to avoid impacting system performance.


## Optimizing Slow Queries

On the Query Engine page in analytics v2.3, indexing hints are used to optimize query performance by specifying the columns to be included in the index. This can significantly reduce the time it takes to execute complex queries. To add an indexing hint, select the columns you want to include in the index from the available columns list and click the "Add" button. You can also remove existing indexing hints by clicking the "Remove" button next to the hint.

To further narrow down the time range of your query, use the "Time Range" dropdown menu to select a specific time period. The available time ranges include the last 1 hour, 24 hours, 7 days, 30 days, and custom time ranges. You can also specify a custom time range by clicking on the "Custom" option and entering a start and end date in the format YYYY-MM-DD HH:MM:SS. Additionally, you can use the "Time Zone" dropdown menu to select the time zone for your query.

When selecting a custom time range, keep in mind that the maximum allowed time range is 31 days. Attempting to select a time range greater than 31 days will result in an error. The "Time Range" and "Time Zone" options are used in conjunction with the indexing hints to optimize query performance and narrow down the time range of your query.
