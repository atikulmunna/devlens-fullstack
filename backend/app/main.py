from urllib.parse import urlparse
import socket
import time

import httpx
from fastapi import FastAPI
from starlette.requests import Request

from app.api.v1 import api_router
from app.config import settings
from app.errors import install_exception_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.observability import begin_trace, http_request_duration_seconds, metrics_response, trace_span

app = FastAPI(title=settings.app_name)
app.add_middleware(RateLimitMiddleware)
app.include_router(api_router, prefix="/api/v1")
install_exception_handlers(app)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start = time.perf_counter()
    trace_id = begin_trace(request)
    path = request.url.path
    method = request.method.upper()

    with trace_span("http.request", method=method, path=path):
        response = await call_next(request)

    duration = time.perf_counter() - start
    http_request_duration_seconds.labels(method=method, path=path, status=str(response.status_code)).observe(duration)
    response.headers["X-Trace-Id"] = trace_id
    return response


def _tcp_check(url: str, default_port: int) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or default_port
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "backend", "env": settings.env}


@app.get("/health/deps")
def health_deps() -> dict:
    redis_ok = _tcp_check(settings.redis_url, 6379)
    postgres_ok = _tcp_check(str(settings.database_url), 5432)

    qdrant_ok = False
    try:
        qdrant_health_url = f"{str(settings.qdrant_url).rstrip('/')}/healthz"
        with httpx.Client(timeout=3.0) as client:
            response = client.get(qdrant_health_url)
            qdrant_ok = response.status_code == 200
    except Exception:
        qdrant_ok = False

    return {
        "redis": redis_ok,
        "postgres": postgres_ok,
        "qdrant": qdrant_ok,
        "all_healthy": redis_ok and postgres_ok and qdrant_ok,
    }


@app.get("/metrics")
def metrics() -> object:
    return metrics_response()
