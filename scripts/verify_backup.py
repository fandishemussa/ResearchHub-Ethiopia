"""Verify a ResearchHub database backup checksum and PostgreSQL archive catalogue."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, *, inspect_archive: bool = True) -> dict[str, object]:
    backup = path.resolve()
    manifest_path = backup.with_suffix(".json")
    if not backup.is_file() or not manifest_path.is_file():
        raise ValueError("Backup and adjacent JSON manifest are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = sha256(backup)
    if manifest.get("sha256") != actual:
        raise ValueError("Backup checksum does not match its manifest")
    if int(manifest.get("size_bytes", -1)) != backup.stat().st_size:
        raise ValueError("Backup size does not match its manifest")
    archive_checked = False
    if inspect_archive:
        if shutil.which("pg_restore") is None:
            raise ValueError("pg_restore was not found on PATH")
        result = subprocess.run(
            ["pg_restore", "--list", str(backup)], capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError(f"pg_restore could not read the archive: {result.stderr.strip()}")
        archive_checked = True
    return {
        "status": "PASS",
        "path": str(backup),
        "sha256": actual,
        "size_bytes": backup.stat().st_size,
        "archive_checked": archive_checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--checksum-only", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.backup, inspect_archive=not args.checksum_only)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "detail": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
