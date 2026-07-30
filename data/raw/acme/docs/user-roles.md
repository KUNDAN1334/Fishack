---
slug: user-roles
title: Users and Roles
tenant: acme
product_area: platform
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# Users and Roles


## Role Types

The Users and Roles page in platform v2.1 defines four distinct access tiers to govern workspace permissions securely. 

The Owner role possesses full administrative control, including billing management, subscription tier modifications, and workspace deletion. This role cannot be assigned to multiple primary accounts simultaneously.

The Admin role manages user provisioning, invitation lifecycles, and general workspace configurations, but is restricted from altering core billing structures or executing destructive workspace actions.

The Analyst role grants full access to reporting engines, data pipeline configurations, and metric dashboards, while prohibiting user management and security settings modifications.

The Viewer role provides read-only access to published dashboards and reports. Viewers cannot modify configurations, export raw datasets, or invite external users. 

Each role maps strictly to these predefined platform permissions without custom overrides.


| Role | Can edit dashboards | Can manage billing | Can invite |
|---|---|---|---|
| Owner | Yes | Yes | Yes |
| Admin | No | No | No |
| Analyst | Yes | Yes | Yes |
| Viewer | No | No | No |


## Inviting Users

Administrators in Flowlytics platform v2.1 can invite new users to their organization directly from the Users and Roles page by entering a valid email address and assigning an initial role. Upon submission, an automated email containing a secure activation link is dispatched to the recipient. 

For security purposes, all invitation links are subject to a strict expiry window of 72 hours from the exact time of generation. If a user fails to accept the invitation and complete their account setup within this 72-hour period, the link becomes invalid, and the system returns an invitation expired status in the user management table. 

When an invitation expires, administrators can easily reinitiate the process by selecting the resend option next to the pending user's profile, which revokes the old token and issues a fresh 72-hour activation link.


## Removing Users

When a user is removed from Flowlytics v2.1 via the Users and Roles page, their assigned dashboards do not automatically delete. Instead, ownership of all private and shared dashboards created by the removed user transfers to the workspace administrator by default. 

Administrators can reassign these dashboards to another active team member or archive them entirely. Any scheduled reports or automated alerts tied to the removed user's account are immediately paused upon removal. Team members who had view or edit permissions via direct sharing retain their access levels until the workspace administrator modifies the dashboard settings. 

To prevent interruption to ongoing operations, ensure dashboard ownership is reassigned before completing the user removal process in platform version 2.1.
