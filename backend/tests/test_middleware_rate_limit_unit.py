from app.middleware.rate_limit import RateLimitMiddleware


def test_limited_prefix_rules() -> None:
    assert RateLimitMiddleware._limited_prefix({"method": "POST", "path": "/api/v1/repos/analyze"}) == "analyze"
    assert RateLimitMiddleware._limited_prefix({"method": "POST", "path": "/api/v1/chat/sessions/1/message"}) == "chat"
    assert RateLimitMiddleware._limited_prefix({"method": "GET", "path": "/api/v1/repos/analyze"}) is None


def test_identity_prefers_forwarded_for_without_auth() -> None:
    identity_type, identity_value = RateLimitMiddleware._identity(
        {"headers": [(b"x-forwarded-for", b"203.0.113.10, 203.0.113.11")], "client": ("127.0.0.1", 1234)}
    )
    assert identity_type == "guest"
    assert identity_value == "203.0.113.10"
