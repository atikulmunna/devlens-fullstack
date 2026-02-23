from contextlib import contextmanager
import logging
import time

from prometheus_client import Histogram, start_http_server


logger = logging.getLogger("devlens.worker.telemetry")

stage_duration_seconds = Histogram(
    "devlens_analysis_stage_duration_seconds",
    "Duration of analysis worker stages.",
    ["stage", "status"],
)


def start_metrics_server(port: int) -> None:
    try:
        start_http_server(port)
    except OSError:
        logger.warning("metrics server bind failed on port %s", port)


def record_stage_duration(stage: str, status: str, duration_seconds: float) -> None:
    stage_duration_seconds.labels(stage=stage, status=status).observe(max(duration_seconds, 0.0))


@contextmanager
def trace_span(name: str, trace_id: str, **attributes):
    started = time.perf_counter()
    logger.info("span.start name=%s trace_id=%s attrs=%s", name, trace_id, attributes)
    try:
        yield
    finally:
        duration = time.perf_counter() - started
        logger.info("span.end name=%s trace_id=%s duration_s=%.6f", name, trace_id, duration)
