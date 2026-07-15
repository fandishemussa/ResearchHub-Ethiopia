# Scaling operations

```powershell
docker compose up -d --scale api=3
docker compose --profile scaling up -d
docker compose --profile observability up -d
docker compose --profile pgbouncer up -d
```

Nginx listens on API port 8111 and the combined application port 8080. API containers expose their port only inside the network, allowing replicas. Recalculate the PostgreSQL connection budget before adding replicas or Celery processes. Scale queue consumers independently from API replicas and observe queue delay, CPU, memory, and database utilization after each change.
