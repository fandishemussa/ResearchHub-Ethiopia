# Enterprise Prototype Performance Results

**Status: NOT_MEASURED**  
**Report date:** 2026-07-16

No defensible capacity or concurrent-user claim is available. The current Windows host did not
have the required Python 3.13 runtime or a running API/PostgreSQL/Redis stack during this audit, so
latency and throughput values are deliberately not invented.

| Workload | Users | RPS | P50 | P95 | P99 | Error rate | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| Catalogue search | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Publication detail | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Semantic search | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Assistant request | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending Ollama model |
| Source list | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Dashboard | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Document chunks | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |

## Required test record

Each executed profile must record CPU model/count, RAM, disk, OS, Docker Desktop resources,
Compose overrides, API replica count, Celery worker count/concurrency, PostgreSQL parameters,
PgBouncer use, database row/vector counts, Redis limits, Ollama model and quantization, embedding
device, test duration and warm-up policy. Capture API RPS/P50/P95/P99/error rate, database pool use,
Redis connections, queue depth, CPU and memory.

Use the existing load-test foundations described in `docs/operations/load-testing.md`. Run a
read-only baseline first, then isolated semantic and AI profiles. Never mix model cold-start time
with steady-state results without reporting both.

## Acceptance policy

Targets must be agreed with Haramaya University ICT and research-office stakeholders after
representative corpus sizing. A passing prototype demonstration is not a production capacity test.
Any future number in this document must link to the exact test configuration and raw result file.
