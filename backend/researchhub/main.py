"""FastAPI application factory for ResearchHub Ethiopia."""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol, cast

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from researchhub.api.v1.router import api_router
from researchhub.core.config import get_settings
from researchhub.core.logging import configure_logging
from researchhub.core.middleware import RequestControlMiddleware
from researchhub.infrastructure.persistence.session import SessionLocal, engine
from researchhub.infrastructure.redis import create_redis_client


class PoolMetrics(Protocol):
    def size(self) -> int: ...

    def checkedin(self) -> int: ...

    def checkedout(self) -> int: ...

    def overflow(self) -> int: ...


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    if settings.app_env.casefold() in {"production", "prod"} and (
        len(settings.auth_jwt_secret) < 32
        or settings.auth_jwt_secret.startswith("development-only")
    ):
        raise RuntimeError("Production requires a strong RESEARCHHUB_AUTH_JWT_SECRET")
    configure_logging(settings.log_level)
    instance_id = settings.instance_id or os.getenv("HOSTNAME") or socket.gethostname()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.instance_id = instance_id
        app.state.started_at = datetime.now(UTC)
        app.state.redis = create_redis_client()
        app.state.http = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.http_connect_timeout_seconds,
                read=settings.http_read_timeout_seconds,
                write=settings.http_write_timeout_seconds,
                pool=settings.http_connect_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive_connections,
            ),
        )
        yield
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI-powered research information management platform for Ethiopia.",
        lifespan=lifespan,
    )
    app.add_middleware(
        RequestControlMiddleware,
        max_concurrent=settings.api_max_concurrent_requests,
        max_body_bytes=settings.max_request_body_mb * 1024 * 1024,
        max_upload_body_bytes=(settings.import_max_file_size_mb + 1) * 1024 * 1024,
        slow_request_ms=settings.slow_request_threshold_ms,
        instance_id=instance_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["system"])
    @app.get("/health/live", tags=["system"])
    async def health() -> dict[str, str]:
        """Return API health status."""

        return {"status": "ok", "instance_id": instance_id}

    async def dependency_status(request: Request) -> tuple[dict[str, str], bool]:
        checks: dict[str, str] = {}
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception:
            checks["postgres"] = "unavailable"
        try:
            checks["redis"] = "ok" if await request.app.state.redis.ping() else "unavailable"
        except Exception:
            checks["redis"] = "unavailable"
        return checks, all(value == "ok" for value in checks.values())

    @app.get("/health/ready", tags=["system"])
    async def readiness(request: Request) -> JSONResponse:
        checks, ready = await dependency_status(request)
        return JSONResponse(
            {"status": "ready" if ready else "unavailable", "instance_id": instance_id, "checks": checks},
            status_code=200 if ready else 503,
        )

    @app.get("/health/dependencies", tags=["system"])
    async def dependencies(request: Request) -> JSONResponse:
        checks, ready = await dependency_status(request)
        return JSONResponse(
            {"status": "ok" if ready else "degraded", "instance_id": instance_id, "checks": checks},
            status_code=200 if ready else 503,
        )

    @app.get("/health/metrics-summary", tags=["system"])
    async def metrics_summary() -> dict[str, object]:
        pool = cast(PoolMetrics, engine.pool)
        return {
            "instance_id": instance_id,
            "database_pool": {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            },
        }

    @app.get(settings.metrics_path, response_class=PlainTextResponse, tags=["system"])
    async def metrics() -> str:
        """Expose a minimal Prometheus-compatible health metric."""

        pool = cast(PoolMetrics, engine.pool)
        return "".join(
            [
                "# TYPE researchhub_api_up gauge\nresearchhub_api_up 1\n",
                f'researchhub_db_pool_size{{instance="{instance_id}"}} {pool.size()}\n',
                f'researchhub_db_pool_checked_out{{instance="{instance_id}"}} {pool.checkedout()}\n',
                f'researchhub_db_pool_overflow{{instance="{instance_id}"}} {pool.overflow()}\n',
            ]
        )

    return app


app = create_app()
