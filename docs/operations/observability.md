# Observability

Every response includes request and instance IDs. Structured logs include those IDs and request duration; requests above the configured threshold are warnings. `/health/live` is process-only. `/health/ready` and `/health/dependencies` check PostgreSQL and Redis. `/health/metrics-summary` exposes pool state and `/metrics` provides Prometheus gauges.

Alert on readiness failures, HTTP error rate, p95/p99 latency, pool saturation/timeouts, PostgreSQL locks, Redis errors, queue depth, task failure/retry duration, disk growth, and worker heartbeat loss. Do not log tokens, passwords, private prompts, uploaded content, or database URLs with credentials.
