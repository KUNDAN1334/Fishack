---
slug: globex-private-link
title: Globex PrivateLink Setup
tenant: globex
product_area: platform
doc_version: v1.0
effective_date: 2026-02-25
source_type: docs
---


# Globex PrivateLink Setup


## PrivateLink Endpoints

To establish Globex-only AWS PrivateLink connectivity, follow these steps on the 'Globex PrivateLink Setup' page. 

First, ensure your account is provisioned for AWS PrivateLink connectivity. This involves verifying your AWS account is enabled for PrivateLink and that the necessary IAM roles and permissions are in place. The required permissions include `ec2:CreateVpcEndpoint` and `ec2:DescribeVpcEndpoints`.

Next, navigate to the 'Globex PrivateLink Setup' page and select the Globex service you wish to connect via PrivateLink. You will then be prompted to enter your AWS account ID and the VPC ID where you want to create the PrivateLink endpoint.

Once you have entered the required information, click 'Create PrivateLink Endpoint' to initiate the setup process. Flowlytics will then create a PrivateLink endpoint in your specified VPC, establishing a secure connection to the Globex service. The entire process should take approximately 30 minutes to complete.


## DNS Configuration

To establish a secure connection through the Globex PrivateLink Setup in Flowlytics platform v1.0, you must configure specific private DNS records within your virtual private cloud. These DNS records map the service endpoints directly to your internal network infrastructure without traversing the public internet. 

Ensure you create a CNAME record for the primary ingestion endpoint pointing to `privatelink.flowlytics.io`. For billing data synchronization, configure a corresponding CNAME record mapping to `billing-privatelink.flowlytics.io`. All DNS resolutions must query your internal resolvers exclusively. 

Failure to configure these exact DNS records will result in connection timeout error `PL-504` during the validation phase. Verify that your internal TTL is set to 60 seconds to ensure rapid failover handling during maintenance windows.
