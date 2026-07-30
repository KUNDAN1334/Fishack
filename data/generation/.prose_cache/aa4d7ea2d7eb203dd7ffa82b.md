The drop in your event volume was caused by a recent ad blocker update that began blocking calls made directly to our standard JavaScript SDK endpoint. 

To resolve this issue, you need to migrate your implementation to route events through a first-party proxy endpoint. This configuration bypasses ad blocker filters by routing telemetry through your own domain before it reaches Flowlytics. 

Please update your SDK initialization to point to your new proxy URL as detailed in our custom domain routing documentation. Once deployed, event collection will resume normal volume immediately. Let us know if you need assistance configuring your proxy.