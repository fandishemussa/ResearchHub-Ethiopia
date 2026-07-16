# Enterprise Prototype Operations Runbook

## Preconditions

- Docker Desktop/Compose or a Python 3.13 local environment.
- `.env` created from `.env.example`, with a unique JWT secret and deployment-specific passwords.
- No database, Redis, Ollama or metrics port exposed beyond the approved host/network.
- A complete Ollama model is optional for local extractive mode and required for the configured
  Ollama generative mode.

## Start and verify

```powershell
docker compose config --quiet
docker compose build
docker compose up -d postgres redis
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose up -d api worker frontend nginx prometheus grafana
docker compose ps
python scripts/check_claimed_features.py --api-url http://localhost:8111 --frontend-url http://localhost:3000 --pretty
```

Add `-f docker-compose.ollama.yml` consistently to every Compose command when Ollama is enabled.
Do not delete the `ollama-data` volume to recover from an interrupted model pull; restart the named
pull helper or rerun `ollama pull`, which reuses verified blobs.

## Stop, restart and shutdown

```powershell
docker compose stop
docker compose restart api worker frontend
docker compose down
```

`down` does not remove named volumes unless `--volumes` is supplied. Never add `--volumes` during
normal maintenance.

## Migration

```powershell
docker compose run --rm api alembic -c backend/alembic.ini heads
docker compose run --rm api alembic -c backend/alembic.ini current
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
```

Require one head and a current database before starting workers. Back up first. Do not edit an
applied migration or auto-generate destructive changes without reviewing SQL.

## Administrator and demo provisioning

```powershell
docker compose exec api python scripts/create_admin_user.py --email <approved-email> --username <approved-username> --full-name "Platform Administrator"
docker compose exec api python scripts/seed_enterprise_demo.py --confirm-demo-seed
docker compose exec api python scripts/verify_enterprise_demo.py
```

The admin command prompts without echo. For automation, inject the documented password environment
variable through a secret store. Do not put passwords in commands or source control.

## Backup and restore

```powershell
python scripts/backup_database.py --dry-run
python scripts/backup_database.py --backup-dir D:\ResearchHubBackups\database --retention 7
python scripts/verify_backup.py D:\ResearchHubBackups\database\researchhub-<timestamp>.dump
python scripts/backup_documents.py --source data\documents --backup-dir D:\ResearchHubBackups\documents
```

Restore only into an isolated empty database after verification:

```powershell
python scripts/restore_database.py D:\ResearchHubBackups\database\researchhub-<timestamp>.dump --confirm-database <exact-target-database>
```

The restore tool does not drop or clean existing objects. A restore into a non-empty database is
expected to fail safely. Record a successful isolated restore drill before relying on the backup.

## Incident triage

1. Capture `docker compose ps` and timestamps; do not restart everything immediately.
2. Check `/health/live`, `/health/ready`, `/health/dependencies`, `/metrics` and Grafana targets.
3. Inspect scoped logs: `docker compose logs --since 15m api worker postgres redis`.
4. Confirm disk space, database connections, Redis availability and queue depth.
5. Preserve failed job IDs/request IDs. Never paste tokens, passwords, full prompts or documents into
   tickets.

### Failed harvest/import

Open the job detail, preserve events/failures/checkpoint, confirm the source is enabled and test its
connection. Retry failed records when supported; otherwise resume/retry the job. Do not start a
second full harvest while the source lock is active.

### Failed indexing

Confirm the file remains under the managed document root, checksum and MIME are valid, extraction
dependencies exist, and the embedding model dimension is 384. Reprocess only the failed document;
do not delete the source PDF as a first response.

### Ollama recovery

Check container health, `ollama list`, available RAM/disk and the configured base URL/model. An EOF
during pull is normally a network interruption: restart the resumable pull, retain the volume, and
verify the model appears in `ollama list` before enabling the provider.

The recovery downloader validates the registry `Content-Range`, writes raw response bytes, and
checks every completed blob against the manifest SHA-256 digest. A legacy `.manual-part-*` cache
from the older downloader is intentionally discarded because it cannot be proven byte-correct.
After an interrupted v2 download, restart the same recovery container to resume its validated
`.manual-v2-*` ranges. If final verification fails, the corrupt range cache is removed rather than
reassembled in a restart loop.

## Rollback

Application rollback means redeploying the last tested image while retaining the current database.
Database downgrade is not the default rollback path. Restore is a separately approved disaster-
recovery action after a verified backup and impact review.

## Log locations

Container logs use `docker compose logs`; application logs are structured stdout/stderr. PostgreSQL,
Redis, Nginx, Prometheus and Grafana logs are service-specific. Imported files and documents live at
configured managed paths; never expose those paths through API responses or support screenshots.
