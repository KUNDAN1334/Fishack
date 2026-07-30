---
slug: webhooks-security
title: Webhook Security
tenant: acme
product_area: platform
doc_version: v2.2
effective_date: 2026-03-12
source_type: docs
---


# Webhook Security


## Signature Verification

To verify the authenticity of incoming webhooks, Flowlytics uses an HMAC-SHA256 signature in the X-Flowlytics-Signature header. This signature is generated using a shared secret key between your application and Flowlytics.

The signature is calculated by taking the HTTP request body and encoding it as UTF-8 bytes. The encoded bytes are then hashed using the HMAC-SHA256 algorithm with the shared secret key. The resulting hash is a 256-bit (32-byte) value, which is then encoded as a hexadecimal string.

To verify the signature, your application should compare the provided X-Flowlytics-Signature header with the expected signature generated using the same shared secret key and the incoming request body. If the two signatures match, the request is considered authentic and can be processed. Flowlytics recommends using a secure method to store and handle the shared secret key.


## Secret Rotation

To rotate the signing secret without downtime, Flowlytics employs a dual-secret window approach on the Webhook Security page (platform, v2.2). This method ensures seamless integration with your application while maintaining the highest level of security.

When rotating your signing secret, you can configure two secrets simultaneously: an active secret and a standby secret. The active secret remains unchanged until the specified rotation deadline, at which point it will be replaced by the standby secret. This transition occurs without interrupting your webhook connections, ensuring uninterrupted data processing.

During the rotation period, Flowlytics will continue to verify incoming webhooks using both secrets. This dual-secret window allows for a smooth transition and minimizes potential disruptions to your application. By configuring a rotation deadline and standby secret, you can maintain the security of your webhooks and avoid downtime during the secret rotation process.


## IP Allowlisting

On the Webhook Security page, customers can allowlist static egress IP ranges to ensure secure communication between their applications and the Flowlytics platform. The following IP ranges can be allowed:

- 35.199.88.0/22
- 52.89.148.0/22
- 35.187.128.0/22
- 52.89.152.0/22

Allowing these IP ranges enables the platform to securely send notifications and updates to customers' applications via webhooks. By whitelisting these IP addresses, customers can prevent potential security threats and ensure that their applications receive authorized data from the Flowlytics platform. It is essential to allow these IP ranges to maintain secure communication and prevent disruptions in data exchange.


| Region | IP range | Since |
|---|---|---|
| us-east | Standard | v2.2 |
| eu-central | Extended | v2.2 |
| eu-west | Custom | v2.2 |
