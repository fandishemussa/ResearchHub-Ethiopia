"""Restore a verified PostgreSQL backup into an explicitly confirmed database."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from verify_backup import verify


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--confirm-database", required=True, help="Exact target database name")
    args = parser.parse_args()
    raw = os.getenv("RESEARCHHUB_SYNC_DATABASE_URL") or os.getenv("RESEARCHHUB_DATABASE_URL")
    if not raw:
        raise SystemExit("RESEARCHHUB_SYNC_DATABASE_URL is required")
    parsed = urlsplit(
        raw.replace("postgresql+psycopg://", "postgresql://").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
    )
    database = unquote(parsed.path.lstrip("/"))
    if not database or args.confirm_database != database:
        raise SystemExit("Confirmation does not exactly match the configured target database")
    if shutil.which("pg_restore") is None:
        raise SystemExit("pg_restore was not found on PATH")
    try:
        verified = verify(args.backup, inspect_archive=True)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Backup verification failed: {exc}") from exc
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    command = [
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        "--host",
        parsed.hostname or "localhost",
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or "postgres"),
        "--dbname",
        database,
        str(args.backup.resolve()),
    ]
    print("WARNING: restoring into a non-empty database may fail on existing objects.")
    result = subprocess.run(command, env=environment, check=False)
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(
        json.dumps({"status": status, "database": database, "backup": verified["path"]}, indent=2)
    )
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
