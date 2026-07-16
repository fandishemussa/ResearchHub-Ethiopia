"""Print a machine-readable verification report for claimed platform surfaces."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


ROUTE_GROUPS = {
    "source_routes": ("/api/sources",),
    "harvest_routes": ("/api/harvest/jobs",),
    "import_routes": ("/api/import/json", "/api/import/csv", "/api/import/xml"),
    "publication_routes": ("/api/publications", "/api/search/publications"),
    "document_routes": ("/api/documents",),
    "ai_routes": ("/api/ai/chat/query",),
    "authentication": ("/api/auth/login", "/api/auth/me"),
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8111")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def fetch_json(url: str, timeout: float) -> tuple[int, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ResearchHubVerifier/1"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator supplied URL
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def http_check(name: str, url: str, timeout: float, accepted: set[int]) -> Check:
    try:
        status, _ = fetch_json(url, timeout)
        if status in accepted:
            return Check(name, "PASS", f"HTTP {status}: {url}")
        return Check(name, "FAIL", f"HTTP {status}: {url}")
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return Check(name, "UNAVAILABLE", f"{url}: {type(exc).__name__}: {exc}")


def migration_check() -> Check:
    command = [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "heads"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("migrations", "UNAVAILABLE", f"{type(exc).__name__}: {exc}")
    heads = [line for line in result.stdout.splitlines() if "(head)" in line]
    if result.returncode == 0 and len(heads) == 1:
        return Check("migrations", "PASS", heads[0].strip())
    detail = (result.stderr or result.stdout or "No Alembic head returned").strip()
    return Check("migrations", "FAIL", detail[-1000:])


def route_checks(api_url: str, timeout: float) -> list[Check]:
    try:
        status, payload = fetch_json(f"{api_url}/openapi.json", timeout)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [
            Check(name, "UNAVAILABLE", f"OpenAPI unavailable: {type(exc).__name__}: {exc}")
            for name in ROUTE_GROUPS
        ]
    if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
        return [Check(name, "FAIL", "OpenAPI response was invalid") for name in ROUTE_GROUPS]
    paths = set(payload["paths"])
    results: list[Check] = []
    for name, required in ROUTE_GROUPS.items():
        missing = [path for path in required if path not in paths]
        results.append(
            Check(name, "FAIL" if missing else "PASS", f"Missing: {', '.join(missing)}" if missing else "Required paths declared")
        )
    return results


def dependency_checks(api_url: str, timeout: float) -> list[Check]:
    try:
        status, payload = fetch_json(f"{api_url}/health/dependencies", timeout)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        detail = f"Dependency endpoint unavailable: {type(exc).__name__}: {exc}"
        return [Check("database", "UNAVAILABLE", detail), Check("redis", "UNAVAILABLE", detail)]
    checks = payload.get("checks", {}) if isinstance(payload, dict) else {}
    results = []
    for name, reported_name in (("database", "postgres"), ("redis", "redis")):
        value = checks.get(reported_name)
        healthy = value is True or value == "ok" or (isinstance(value, dict) and value.get("status") == "ok")
        results.append(Check(name, "PASS" if healthy else "FAIL", f"HTTP {status}; reported={value!r}"))
    return results


def main() -> int:
    args = arguments()
    api_url = args.api_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    checks = [
        *dependency_checks(api_url, args.timeout),
        migration_check(),
        *route_checks(api_url, args.timeout),
        http_check("metrics", f"{api_url}/metrics", args.timeout, {200}),
        http_check("frontend_health", frontend_url, args.timeout, {200, 301, 302, 307, 308}),
    ]
    report = {
        "status": "PASS" if all(item.status == "PASS" for item in checks) else "INCOMPLETE",
        "checks": [asdict(item) for item in checks],
    }
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
