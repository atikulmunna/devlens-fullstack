from uuid import uuid4

from fastapi import Request

from app import observability


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/test",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "scheme": "http",
        "query_string": b"",
        "server": ("test", 80),
    }
    return Request(scope)


def test_begin_trace_uses_incoming_header() -> None:
    req = _request_with_headers([(b"x-trace-id", b"trace-123")])
    trace_id = observability.begin_trace(req)
    assert trace_id == "trace-123"


def test_begin_trace_generates_when_missing() -> None:
    req = _request_with_headers([])
    trace_id = observability.begin_trace(req)
    assert isinstance(trace_id, str)
    assert len(trace_id) == 32


def test_metrics_response_has_prometheus_content_type() -> None:
    response = observability.metrics_response()
    assert "text/plain" in response.media_type


def test_trace_span_executes() -> None:
    with observability.trace_span("unit.test", step="x"):
        assert True


def test_request_metrics_are_labeled_by_route_template_not_raw_path(client) -> None:
    repo_id = uuid4()
    client.get(f"/api/v1/repos/{repo_id}/dashboard")  # matched route; the handler answers 404
    client.get(f"/no-such-route/{repo_id}")  # matches no route at all

    metrics = client.get("/metrics").text
    counts = [line for line in metrics.splitlines() if line.startswith("devlens_http_request_duration_seconds_count")]

    assert any('path="/api/v1/repos/{repo_id}/dashboard"' in line for line in counts)
    assert any('path="unmatched"' in line for line in counts)
    # Raw paths embed ids, which would create one time series per repo (unbounded cardinality).
    assert str(repo_id) not in metrics
