"""Shared async Redis client.

`Redis.from_url` builds its own connection pool, so creating one per request (as the
rate-limit middleware previously did) churns pools and connections on every hot-path call.
This module hands out a single lazily-created client reused for the app's lifetime.
"""

from redis.asyncio import Redis

from app.config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
