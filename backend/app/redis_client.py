"""Shared async Redis client.

`Redis.from_url` builds its own connection pool, so creating one per request (as the
rate-limit middleware previously did) churns pools and connections on every hot-path call.
This module hands out a single client reused for the app's lifetime.

An async Redis client is bound to the event loop it first ran on. The app serves on one
loop in production, but tests (and any multi-loop caller) can run on different loops, so
the client is cached per running loop and recreated when the loop changes. Without this,
a loop mismatch raises and the middleware fails open, silently disabling rate limiting.
"""

import asyncio

from redis.asyncio import Redis

from app.config import settings

_client: Redis | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_redis() -> Redis:
    global _client, _client_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _client is None or _client_loop is not loop:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
        _client_loop = loop
    return _client


async def close_redis() -> None:
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None
