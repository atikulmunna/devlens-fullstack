# Backend Service

FastAPI API service for DevLens.

## Local

1. Copy `.env.example` to `.env`.
2. Install dependencies from `requirements.txt`.
3. Start with `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
4. Run migrations with `alembic -c alembic.ini upgrade head`.

## Observability

- Request latency histogram: `devlens_http_request_duration_seconds` (available at `/metrics`).
- SSE first-event latency histogram: `devlens_sse_startup_latency_seconds` (available at `/metrics`).
- All HTTP responses include `X-Trace-Id` for trace correlation.
