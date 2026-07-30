---
slug: api-authentication
title: API Authentication
tenant: acme
product_area: platform
doc_version: v2.3
effective_date: 2026-04-02
source_type: docs
---


# API Authentication


## API Keys

To create a new API key, navigate to the 'API Authentication' page in the dashboard and click the 'Create API Key' button. You will be prompted to enter a name for the key and select the scopes it should be granted. Scopes determine the level of access the API key has to your Flowlytics account, and you can choose from the following options: 'Read', 'Write', and 'Admin'. 

When creating a new API key, you can also specify a custom label to help identify it. Once created, you can view and manage all API keys from the 'API Keys' table. To revoke an API key, click the 'Revoke' button next to the key you wish to disable. This will immediately terminate access to your Flowlytics account via that API key. Note that revoked API keys can be recreated at any time.


## Bearer Token Usage

To authenticate API requests, you must include a valid Authorization header in your request. The header format is as follows: `Authorization: Bearer <access_token>`, where `<access_token>` is a unique token obtained after successful authentication. 

You can obtain an access token by sending a POST request to the `/oauth/token` endpoint with your client ID and client secret. 

Here is an example using curl:
```bash
curl -X POST \
  https://your-domain.com/oauth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET'
```
Replace `https://your-domain.com` with your actual domain and `YOUR_CLIENT_ID` and `YOUR_CLIENT_SECRET` with your actual client ID and client secret. 

Note that the `client_credentials` grant type is used for server-to-server authentication.


## Key Rotation

To perform a zero-downtime rotation procedure for API authentication, follow these steps:

1. Create a new API key on the 'API Authentication' page.
2. Note the new API key's ID and secret.
3. Update the API key ID and secret in your application's configuration.
4. Test API requests using the new credentials to ensure functionality.
5. Once confirmed, update the 'API Authentication' page to set the new API key as active.
6. Set the previously active API key to 'inactive' on the 'API Authentication' page.
7. Delete the old API key from your application's configuration.

This procedure allows for seamless rotation of API keys without disrupting service. When updating the 'API Authentication' page, ensure the 'active' API key is set to the new key ID and secret to maintain uninterrupted access.


## Scopes and Permissions

On the API Authentication page, Flowlytics allows administrators to configure read and write scopes for each resource. This enables fine-grained control over the level of access granted to API clients. 

For each resource, administrators can select from the following scopes:

- Read: Allows API clients to retrieve data from the resource.
- Write: Allows API clients to create, update, or delete data in the resource.
- Both: Grants both read and write access to the resource.

By configuring scopes at the resource level, administrators can ensure that API clients only have access to the data they need, reducing the risk of unauthorized data access or modifications. This approach also simplifies permission management and auditing, as the access rights for each resource are clearly defined. The configured scopes apply to all API clients, unless overridden at the client level.


| Scope | Grants | Required plan |
|---|---|---|
| events:read | Standard | Yes |
| events:write | Extended | No |
| billing:read | Custom | Yes |
