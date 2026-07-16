"""Run the documented search query set and save reproducible raw rankings."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request_json(url: str, timeout: float) -> tuple[int, Any, float]:
    started = time.perf_counter()
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ResearchHubSearchEvaluation/1"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator supplied URL
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload, (time.perf_counter() - started) * 1000
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace"), (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8111")
    parser.add_argument("--queries", type=Path, default=Path("data/search_evaluation_queries.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/search-evaluation-results.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 50:
        raise SystemExit("--top-k must be between 1 and 50")
    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    if not isinstance(queries, list):
        raise SystemExit("Query dataset must contain a JSON array")
    results = []
    failures = 0
    for item in queries:
        if not isinstance(item, dict) or not isinstance(item.get("query"), str):
            continue
        query = item["query"]
        variants = {}
        for variant, path, parameter in (
            ("lexical", "/api/search/publications", "query"),
            ("publication_semantic", "/api/search/semantic", "q"),
        ):
            url = f"{args.api_url.rstrip('/')}{path}?{urlencode({parameter: query, 'limit': args.top_k})}"
            try:
                status, payload, duration = request_json(url, args.timeout)
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                status, payload, duration = 0, {"error": f"{type(exc).__name__}: {exc}"}, 0.0
            if status != 200:
                failures += 1
            variants[variant] = {"status": status, "duration_ms": round(duration, 2), "response": payload}
        results.append({"id": item.get("id"), "query": query, "intent": item.get("intent"), "variants": variants})
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "api_url": args.api_url,
        "top_k": args.top_k,
        "query_dataset": str(args.queries),
        "metrics": "NOT_COMPUTED_WITHOUT_RELEVANCE_LABELS",
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS" if failures == 0 else "INCOMPLETE", "queries": len(results), "failed_requests": failures, "output": str(args.output)}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
