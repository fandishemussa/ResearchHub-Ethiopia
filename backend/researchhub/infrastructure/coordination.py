"""Redis-backed coordination primitives shared by all API instances."""

from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe

from redis.asyncio import Redis

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_RATE_LIMIT_SCRIPT = """
local current = redis.call('incr', KEYS[1])
if current == 1 then redis.call('expire', KEYS[1], ARGV[1]) end
local ttl = redis.call('ttl', KEYS[1])
return {current, ttl}
"""


class LockNotAcquiredError(RuntimeError):
    pass


class DistributedLock:
    def __init__(self, redis: Redis, name: str, *, ttl_seconds: int = 60) -> None:
        self.redis = redis
        self.key = f"researchhub:lock:{name}"
        self.ttl_seconds = ttl_seconds
        self.owner = token_urlsafe(24)
        self.acquired = False

    async def acquire(self) -> bool:
        self.acquired = bool(
            await self.redis.set(self.key, self.owner, ex=self.ttl_seconds, nx=True)
        )
        return self.acquired

    async def renew(self) -> bool:
        if not self.acquired:
            return False
        return bool(await self.redis.eval(_RENEW_SCRIPT, 1, self.key, self.owner, self.ttl_seconds))

    async def release(self) -> bool:
        if not self.acquired:
            return False
        released = bool(await self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.owner))
        self.acquired = False
        return released

    async def __aenter__(self) -> DistributedLock:
        if not await self.acquire():
            raise LockNotAcquiredError(f"Lock '{self.key}' is already held")
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.release()


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


async def check_rate_limit(
    redis: Redis,
    group: str,
    subject: str,
    *,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    key = f"researchhub:rate-limit:{group}:{subject}"
    count, ttl = await redis.eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds)
    count = int(count)
    ttl = max(int(ttl), 0)
    return RateLimitResult(
        allowed=count <= limit,
        limit=limit,
        remaining=max(limit - count, 0),
        retry_after=ttl,
    )
