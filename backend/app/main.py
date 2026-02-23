from urllib.parse import urlparse
import socket

import httpx
from fastapi import FastAPI

from app.config import settings

app = FastAPI(title=settings.app_name)


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
    postgres_ok = _tcp_check(settings.database_url, 5432)

    qdrant_ok = False
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{settings.qdrant_url}/healthz")
            qdrant_ok = response.status_code == 200
    except Exception:
        qdrant_ok = False

    return {
        "redis": redis_ok,
        "postgres": postgres_ok,
        "qdrant": qdrant_ok,
        "all_healthy": redis_ok and postgres_ok and qdrant_ok,
    }
