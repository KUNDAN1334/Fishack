---
slug: billing-tax
title: Tax and Compliance
tenant: globex
product_area: billing
doc_version: v2.1
effective_date: 2026-02-18
source_type: docs
---


# Tax and Compliance


## VAT and Sales Tax

Flowlytics billing v2.1 determines applicable taxes based on the primary billing address associated with your organization's workspace. When an invoice is generated, the system validates the country, state or province, and postal code provided in your billing profile against real-time tax jurisdiction databases. If the address is incomplete or invalid, calculation defaults to the highest applicable regional rate until updated. 

To ensure accurate tax assessment, verify that your billing address matches your official registered business location. You can update these details at any time by navigating to the billing settings page. Changes take effect on the next billing cycle. For tax-exempt organizations, valid exemption certificates must be uploaded directly to your account dashboard for manual verification and processing by our finance team.


## Tax Exemption

Navigate to the Tax and Compliance page in billing version v2.1 to submit a tax exemption certificate. Click the Upload Certificate action and attach your valid documentation in PDF, PNG, or JPEG format, ensuring the file size does not exceed 15 MB. Select the applicable tax jurisdiction and enter the exact expiration date as stated on your official document. 

Once submitted, the system routes your file for automated verification, which typically completes within 24 to 48 hours. During this review period, existing tax calculations remain active on your account. If the validation fails, error code TAX-409 will appear alongside a specific rejection reason, allowing you to re-upload a corrected file. Approved certificates immediately update your tax profile to exempt status for all subsequent billing cycles.


## Invoices for Compliance

In billing version 2.1, all generated invoices carry standardized compliance fields required for cross-border transactions and statutory auditing. Every invoice automatically displays the merchant and customer tax identification numbers, the assigned tax jurisdiction, and the exact statutory tax rate applied to each line item. For businesses operating in Europe and other regulated regions, the document includes the mandatory VAT compliance code and the unique Sequential Invoice Identifier. 

To maintain audit readiness under international financial frameworks, invoices also record the precise UTC timestamp of the transaction, the currency conversion rate if applicable, and the official electronic signature hash. You can configure default compliance labels and exemption text within your tax profile settings, which Flowlytics appends dynamically to all outbound PDF and electronic invoice formats.
