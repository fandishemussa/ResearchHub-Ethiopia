"""Create a timestamped ZIP backup of managed research documents with a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(
            os.getenv("RESEARCHHUB_DOCUMENT_STORAGE_PATH", "data/research-documents")
        ),
    )
    parser.add_argument("--backup-dir", type=Path, default=Path("backups/documents"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"Document directory does not exist: {source}")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = args.backup_dir.resolve() / f"researchhub-documents-{timestamp}.zip"
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite {destination}")
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "files": len(files), "destination": str(destination)}, indent=2))
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            archive.write(path, relative)
            manifest.append({"path": relative, "size_bytes": path.stat().st_size, "sha256": digest})
        archive.writestr("researchhub-backup-manifest.json", json.dumps({"created_at": datetime.now(UTC).isoformat(), "files": manifest}, indent=2))
    print(json.dumps({"status": "PASS", "path": str(destination), "files": len(files), "size_bytes": destination.stat().st_size}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
