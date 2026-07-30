---
slug: sso-setup
title: SSO Setup
tenant: globex
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# SSO Setup


## SAML Configuration

To configure Single Sign-On in Flowlytics platform v2.2, navigate to the SSO Setup page and complete the Identity Provider metadata exchange. First, obtain the Federation Metadata XML file or the metadata URL from your enterprise IdP. Paste the metadata URL into the designated field, or upload the XML file directly using the file picker. Ensure your IdP configuration uses HTTP-POST binding for SAML assertions and includes the correct entity ID matching your Flowlytics account domain. Once uploaded, click Verify Metadata to validate the certificate chain and endpoint URLs. If the exchange fails, check that the IdP signing certificate has not expired and review the error logs. After successful verification, click Save Configuration to enable the SSO login flow for all organization users.


## SCIM Provisioning

The SSO Setup page in platform v2.2 supports automated user provisioning and deprovisioning via the System for Cross-domain Identity Management (SCIM) protocol. When SCIM provisioning is enabled, user creation, role assignments, and profile updates managed in your identity provider automatically synchronize with Flowlytics. 

Deprovisioning a user in your identity provider immediately revokes their access to the Flowlytics platform and terminates all active sessions. To configure this feature, generate a SCIM bearer token within the SSO Setup page and paste it into your identity provider's provisioning configuration along with your unique tenant endpoint URL. Ensure that user attributes, including email and role mappings, match the required Flowlytics schema specifications before initiating the synchronization to avoid provisioning failures or unassigned user states.


## Troubleshooting SSO

When configuring Single Sign-On on the SSO Setup page in platform version v2.2, administrators may encounter common assertion errors during authentication testing and user logins. 

The INVALID_AUDIENCE error occurs when the audience URI sent by the identity provider does not match the expected application identifier configured in Flowlytics. Verify that the entity ID matches exactly across both systems, ensuring there are no trailing slashes or typos.

The SIGNATURE_VERIFICATION_FAILED error indicates that the SAML response or assertion signature is invalid. This typically happens when the identity provider's x.509 certificate has expired, has been rotated without updating Flowlytics, or was imported incorrectly. Upload the current, active certificate to resolve this issue.

The ASSERTION_TIME_INVALID error is triggered when the timestamp validation fails. This is caused by clock skew between the identity provider and Flowlytics servers. Ensure that your identity provider's time synchronization is accurate within the allowable drift tolerance.

The USER_PROVISIONING_FAILED error appears when the SAML assertion lacks required attribute mappings, such as email or external ID, or when the user's role cannot be assigned based on the incoming assertions. Check the attribute statement configuration in your identity provider to confirm all mandatory fields are transmitted correctly.

If you encounter unhandled errors or persistent authentication failures, review the real-time assertion logs available on the SSO Setup page. These logs capture the raw incoming XML payload and specific validation failures to assist with debugging complex integration issues. Ensure your identity provider configuration strictly adheres to SAML 2.0 standards supported by Flowlytics v2.2 to prevent assertion parsing exceptions and ensure seamless user authentication across your organization.
