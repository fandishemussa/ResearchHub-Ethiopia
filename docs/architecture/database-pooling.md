# Database pooling

Pool settings are bounded through `RESEARCHHUB_DB_POOL_*`. Development defaults are five persistent plus five overflow connections per process, a 10-second acquisition timeout, pre-ping, and 30-minute recycling. PostgreSQL statement, lock, and idle-transaction timeouts are applied to every asyncpg connection.

Budget connections before scaling:

```text
total_possible_connections =
  api_instances * (DB_POOL_SIZE + DB_MAX_OVERFLOW)
  + celery_processes * celery_pool_capacity
  + scheduler_connections
  + migration_connections
  + administrative_reserve
```

Keep this below `max_connections`; reserve at least 10 connections for administration and recovery. With PgBouncer transaction pooling, set `RESEARCHHUB_DB_USE_PGBOUNCER=true` to disable asyncpg's prepared-statement cache and point both database URLs at `pgbouncer:5432`. Run migrations directly against PostgreSQL, not through transaction pooling.
