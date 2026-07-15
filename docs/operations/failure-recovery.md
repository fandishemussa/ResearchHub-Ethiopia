# Failure and recovery

PostgreSQL failure makes readiness unhealthy; bounded pool and statement timeouts make requests fail promptly and sessions roll back. Redis cache failure may degrade reads, but lock- or queue-dependent mutations must fail safely. Celery broker loss must not mark unexecuted work complete.

During shutdown, stop accepting new traffic, allow the configured grace period, then close HTTP, Redis, and database pools. Test recovery by terminating one API replica and one worker during non-destructive load. Validate that other replicas continue and durable queued work is redelivered safely.

Backups remain separate from high availability: schedule encrypted PostgreSQL backups, test restore, retain upload/object storage consistently, and document RPO/RTO.
