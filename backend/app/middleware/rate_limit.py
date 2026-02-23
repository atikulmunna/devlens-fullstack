from datetime import UTC, datetime

from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import settings
from app.services.tokens import decode_access_token


LUA_RATE_LIMIT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit_key_prefix = self._limited_prefix(scope)
        if not limit_key_prefix:
            await self.app(scope, receive, send)
            return

        identity_type, identity_value = self._identity(scope)
        limit = settings.rate_limit_auth_per_window if identity_type == "auth" else settings.rate_limit_guest_per_window
        window_seconds = settings.rate_limit_window_seconds
        bucket_key = f"ratelimit:{limit_key_prefix}:{identity_type}:{identity_value}"

        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            count, ttl = await redis_client.eval(LUA_RATE_LIMIT, 1, bucket_key, window_seconds)
            current = int(count)
            ttl_value = int(ttl) if int(ttl) > 0 else window_seconds
        except Exception:
            # Fail-open to preserve availability if redis is temporarily unavailable.
            await self.app(scope, receive, send)
            return
        finally:
            await redis_client.aclose()

        remaining = max(limit - current, 0)
        reset_epoch = int(datetime.now(UTC).timestamp()) + ttl_value
        raw_headers = [
            (b"x-ratelimit-limit", str(limit).encode("ascii")),
            (b"x-ratelimit-remaining", str(remaining).encode("ascii")),
            (b"x-ratelimit-reset", str(reset_epoch).encode("ascii")),
        ]

        if current > limit:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Rate limit exceeded",
                        "details": {"scope": limit_key_prefix, "identity_type": identity_type},
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_epoch),
                    "Retry-After": str(ttl_value),
                },
            )
            await response(scope, receive, send)
            return

        async def send_with_rate_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(raw_headers)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_rate_headers)

    @staticmethod
    def _limited_prefix(scope) -> str | None:
        path = scope.get("path", "")
        method = str(scope.get("method", "")).upper()
        if method == "POST" and path == "/api/v1/repos/analyze":
            return "analyze"
        if method == "POST" and path.startswith("/api/v1/chat"):
            return "chat"
        return None

    @staticmethod
    def _identity(scope) -> tuple[str, str]:
        header_map: dict[str, str] = {}
        for key, value in scope.get("headers", []):
            header_map[key.decode("latin1").lower()] = value.decode("latin1")

        auth_header = header_map.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = decode_access_token(token)
                subject = str(payload.get("sub") or "")
                if subject:
                    return "auth", subject
            except Exception:
                pass

        forwarded_for = header_map.get("x-forwarded-for")
        if forwarded_for:
            return "guest", forwarded_for.split(",")[0].strip()
        client = scope.get("client")
        if client and client[0]:
            return "guest", str(client[0])
        return "guest", "unknown"
