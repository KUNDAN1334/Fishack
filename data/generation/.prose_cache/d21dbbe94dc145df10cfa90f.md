The Flowlytics platform emits the following event types via webhooks:

- **Subscription Created**: Triggered when a new subscription is created, including subscription ID, customer ID, and plan details.
- **Subscription Updated**: Triggered when an existing subscription is updated, including changes to plan details, billing cycle, or customer information.
- **Subscription Canceled**: Triggered when a subscription is canceled, including reason for cancellation and effective date.
- **Invoice Created**: Triggered when a new invoice is generated, including invoice ID, subscription ID, and billing details.
- **Payment Succeeded**: Triggered when a payment is successfully processed, including payment method, amount, and transaction details.
- **Payment Failed**: Triggered when a payment fails, including error code and transaction details.

These event types provide real-time notifications of key events within the platform, enabling seamless integration with external systems and workflows.