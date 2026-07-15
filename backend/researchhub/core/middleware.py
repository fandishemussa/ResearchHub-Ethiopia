"""Bounded request handling and correlation middleware."""

from __future__ import annotations

import asyncio
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


class RequestControlMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        max_concurrent: int,
        max_body_bytes: int,
        max_upload_body_bytes: int,
        slow_request_ms: int,
        instance_id: str,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._capacity = asyncio.Semaphore(max_concurrent)
        self._max_body_bytes = max_body_bytes
        self._max_upload_body_bytes = max_upload_body_bytes
        self._slow_request_ms = slow_request_ms
        self._instance_id = instance_id
        self._logger = structlog.get_logger("http")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", "").strip()[:128] or str(uuid4())
        content_length = request.headers.get("content-length")
        is_import = request.url.path.startswith("/api/import/") or (
            request.url.path.startswith("/api/sources/") and "/import/" in request.url.path
        )
        body_limit = self._max_upload_body_bytes if is_import else self._max_body_bytes
        if content_length and content_length.isdigit() and int(content_length) > body_limit:
            return JSONResponse(
                {
                    "detail": f"Request body exceeds the {body_limit // (1024 * 1024)} MB limit",
                    "code": "request_too_large",
                },
                status_code=413,
                headers={"X-Request-ID": request_id},
            )
        if self._capacity.locked():
            return JSONResponse(
                {"detail": "Server request capacity is exhausted", "code": "overloaded"},
                status_code=503,
                headers={"Retry-After": "1", "X-Request-ID": request_id},
            )
        started = perf_counter()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, instance_id=self._instance_id
        )
        try:
            async with self._capacity:
                response = await call_next(request)
        finally:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            log = self._logger.warning if elapsed_ms >= self._slow_request_ms else self._logger.info
            log(
                "request_completed",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
            )
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        response.headers["X-ResearchHub-Instance"] = self._instance_id
        return response
