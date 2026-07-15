from __future__ import annotations

from typing import Any

import pytest
from researchhub.infrastructure.coordination import DistributedLock, check_rate_limit


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    async def set(self, key: str, value: str, **kwargs: Any) -> bool:
        if kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, _keys: int, key: str, *args: Any) -> Any:
        if "incr" in script:
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], int(args[0])]
        owner = str(args[0])
        if self.values.get(key) != owner:
            return 0
        if "del" in script:
            del self.values[key]
        return 1


@pytest.mark.asyncio
async def test_lock_has_owner_safe_release() -> None:
    redis = FakeRedis()
    first = DistributedLock(redis, "source:1", ttl_seconds=30)  # type: ignore[arg-type]
    second = DistributedLock(redis, "source:1", ttl_seconds=30)  # type: ignore[arg-type]
    assert await first.acquire() is True
    assert await second.acquire() is False
    assert await second.release() is False
    assert await first.renew() is True
    assert await first.release() is True
    assert await second.acquire() is True


@pytest.mark.asyncio
async def test_rate_limit_is_namespaced_and_bounded() -> None:
    redis = FakeRedis()
    first = await check_rate_limit(  # type: ignore[arg-type]
        redis, "login", "subject", limit=2, window_seconds=60
    )
    second = await check_rate_limit(  # type: ignore[arg-type]
        redis, "login", "subject", limit=2, window_seconds=60
    )
    denied = await check_rate_limit(  # type: ignore[arg-type]
        redis, "login", "subject", limit=2, window_seconds=60
    )
    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0
    assert not denied.allowed and denied.retry_after == 60
    assert next(iter(redis.counts)).startswith("researchhub:rate-limit:login:")
