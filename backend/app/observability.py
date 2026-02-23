from contextlib import contextmanager
from contextvars import ContextVar
import logging
import time
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger("devlens.observability")

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

http_request_duration_seconds = Histogram(
    "devlens_http_request_duration_seconds",
    "Duration of HTTP requests.",
    ["method", "path", "status"],
)
sse_startup_latency_seconds = Histogram(
    "devlens_sse_startup_latency_seconds",
    "Latency until first SSE event is emitted.",
    ["endpoint"],
)


def observe_sse_startup(endpoint: str, seconds: float) -> None:
    sse_startup_latency_seconds.labels(endpoint=endpoint).observe(max(seconds, 0.0))


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def current_trace_id() -> str:
    return trace_id_var.get() or ""


def begin_trace(request: Request) -> str:
    incoming = request.headers.get("x-trace-id", "").strip()
    trace_id = incoming or uuid4().hex
    trace_id_var.set(trace_id)
    return trace_id


@contextmanager
def trace_span(name: str, **attributes):
    started = time.perf_counter()
    trace_id = current_trace_id() or uuid4().hex
    logger.info("span.start name=%s trace_id=%s attrs=%s", name, trace_id, attributes)
    try:
        yield
    finally:
        duration = time.perf_counter() - started
        logger.info("span.end name=%s trace_id=%s duration_s=%.6f", name, trace_id, duration)
