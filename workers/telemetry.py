from contextlib import contextmanager
import logging
import time

from prometheus_client import Counter, Histogram, start_http_server


logger = logging.getLogger("devlens.worker.telemetry")

stage_duration_seconds = Histogram(
    "devlens_analysis_stage_duration_seconds",
    "Duration of analysis worker stages.",
    ["stage", "status"],
)

llm_provider_attempts_total = Counter(
    "devlens_llm_provider_attempts_total",
    "LLM provider summary attempts by provider/status/error code.",
    ["provider", "status", "error_code"],
)

llm_fallback_total = Counter(
    "devlens_llm_fallback_total",
    "LLM provider fallback events.",
    ["primary_provider", "fallback_provider", "reason"],
)


def start_metrics_server(port: int) -> None:
    try:
        start_http_server(port)
    except OSError:
        logger.warning("metrics server bind failed on port %s", port)


def record_stage_duration(stage: str, status: str, duration_seconds: float) -> None:
    stage_duration_seconds.labels(stage=stage, status=status).observe(max(duration_seconds, 0.0))


def record_llm_provider_attempt(provider: str, status: str, error_code: str = "none") -> None:
    llm_provider_attempts_total.labels(
        provider=(provider or "unknown").lower(),
        status=(status or "unknown").lower(),
        error_code=(error_code or "none").lower(),
    ).inc()


def record_llm_fallback(primary_provider: str, fallback_provider: str, reason: str) -> None:
    llm_fallback_total.labels(
        primary_provider=(primary_provider or "unknown").lower(),
        fallback_provider=(fallback_provider or "unknown").lower(),
        reason=(reason or "unknown").lower(),
    ).inc()


@contextmanager
def trace_span(name: str, trace_id: str, **attributes):
    started = time.perf_counter()
    logger.info("span.start name=%s trace_id=%s attrs=%s", name, trace_id, attributes)
    try:
        yield
    finally:
        duration = time.perf_counter() - started
        logger.info("span.end name=%s trace_id=%s duration_s=%.6f", name, trace_id, duration)
