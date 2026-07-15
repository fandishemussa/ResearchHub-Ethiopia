# Scalability architecture

ResearchHub API instances are stateless. Durable state belongs in PostgreSQL, short-lived coordination in Redis, uploads in shared mounted/object storage, and asynchronous execution in Celery. Nginx distributes requests across Docker DNS-resolved API replicas and disables buffering for streaming routes.

The initial validation target is 1,000 connected virtual users with at least 200 actively generating requests. This is a test target, not a capacity claim. A capacity claim requires a recorded deployment, hardware profile, latency percentiles, error rate, throughput, database/Redis pool utilization, queue depth, and resource utilization.

Required SLOs under validated normal load: health p95 <100 ms; publication list <500 ms; detail <400 ms; metadata search <800 ms; semantic/similarity search <1.5 s; login <800 ms excluding intentional hashing; refresh <500 ms; job status <300 ms; HTTP errors <1%. Availability target after production infrastructure deployment is 99.9%. AI latency is provider, model, hardware, and prompt dependent and must be reported separately.

API workers expose instance identity in response headers, logs, and health responses. One failed API replica must not stop other replicas; failed background workers must not prevent browsing.
