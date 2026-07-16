"""Create a timestamped PostgreSQL custom-format backup and SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, default=Path("backups/database"))
    parser.add_argument("--retention", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def database_connection() -> tuple[list[str], dict[str, str], str]:
    raw = os.getenv("RESEARCHHUB_SYNC_DATABASE_URL") or os.getenv("RESEARCHHUB_DATABASE_URL")
    if not raw:
        raise RuntimeError("RESEARCHHUB_SYNC_DATABASE_URL is required")
    parsed = urlsplit(raw.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://"))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("The configured database URL is not a PostgreSQL URL")
    database = parsed.path.lstrip("/")
    if not database:
        raise RuntimeError("The database URL does not include a database name")
    command = [
        "--host", parsed.hostname,
        "--port", str(parsed.port or 5432),
        "--username", unquote(parsed.username or "postgres"),
        "--dbname", unquote(database),
    ]
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return command, environment, unquote(database)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    args = arguments()
    if args.retention < 1:
        raise SystemExit("--retention must be at least 1")
    connection, environment, database = database_connection()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = args.backup_dir.resolve() / f"researchhub-{timestamp}.dump"
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite {destination}")
    command = ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", *connection, "--file", str(destination)]
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "database": database, "destination": str(destination), "retention": args.retention}, indent=2))
        return 0
    if shutil.which("pg_dump") is None:
        raise SystemExit("pg_dump was not found on PATH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, env=environment, check=False)
    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise SystemExit(f"pg_dump failed with exit code {result.returncode}")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "database": database,
        "filename": destination.name,
        "size_bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "format": "postgresql-custom",
    }
    destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    backups = sorted(destination.parent.glob("researchhub-*.dump"), key=lambda item: item.stat().st_mtime, reverse=True)
    for expired in backups[args.retention:]:
        expired.unlink()
        expired.with_suffix(".json").unlink(missing_ok=True)
    print(json.dumps({"status": "PASS", **manifest, "path": str(destination)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
