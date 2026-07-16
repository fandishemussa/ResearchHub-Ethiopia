# Backup and Recovery

ResearchHub requires coordinated PostgreSQL and document-storage backups. A database dump alone
cannot restore PDFs; a file archive alone cannot restore publication links, provenance, jobs,
sessions, chunks or document UUIDs.

## Database backup

```powershell
python scripts/backup_database.py --dry-run
python scripts/backup_database.py --backup-dir D:\ResearchHubBackups\database --retention 7
python scripts/verify_backup.py D:\ResearchHubBackups\database\researchhub-<timestamp>.dump
```

The backup is PostgreSQL custom format, has an adjacent JSON SHA-256/size manifest, never silently
overwrites, and applies retention only after a successful non-empty dump. The password is passed to
`pg_dump` through `PGPASSWORD`, not printed or embedded in the command.

## Document backup

Pause write-heavy import/index operations or use storage snapshots with consistent semantics:

```powershell
python scripts/backup_documents.py --source data\research-documents --backup-dir D:\ResearchHubBackups\documents --dry-run
python scripts/backup_documents.py --source data\research-documents --backup-dir D:\ResearchHubBackups\documents
```

The ZIP contains a manifest with each relative path, size and SHA-256. Keep database and file
backups under the same change window and record their timestamps.

## Restore drill

Never test restoration against the active database. Provision an isolated empty database, point
`RESEARCHHUB_SYNC_DATABASE_URL` to it, verify the archive, and supply the exact database name:

```powershell
python scripts/restore_database.py D:\ResearchHubBackups\database\researchhub-<timestamp>.dump --confirm-database researchhub_restore_test
```

The script refuses a mismatched confirmation and does not use `--clean` or drop objects. After
restore, run Alembic `current`, row-count checks, feature verification, document-manifest checks and
a sample publication/document/citation workflow. Record duration and outcome.

## Limitations

Dry runs were validated during the enterprise audit. A real dump and isolated restore were not run
because PostgreSQL was unavailable. Backup status is not yet persisted in an admin database table.
Use external monitoring for backup age/failure until that feature is implemented.
