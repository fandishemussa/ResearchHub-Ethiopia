"""Shared bounded Redis client used by API infrastructure services."""

from typing import cast

from fastapi import Request
from redis.asyncio import Redis

from researchhub.core.config import get_settings


def create_redis_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=settings.redis_max_connections,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_timeout=settings.redis_socket_timeout,
        health_check_interval=settings.redis_health_check_interval,
        retry_on_timeout=settings.redis_retry_on_timeout,
    )


async def get_redis(request: Request) -> Redis:
    """Return the application-scoped Redis client initialized at startup."""

    return cast(Redis, request.app.state.redis)
