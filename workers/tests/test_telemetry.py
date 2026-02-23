from prometheus_client import generate_latest

import telemetry


def test_record_stage_duration_emits_metric_sample() -> None:
    telemetry.record_stage_duration("parsing", "success", 0.25)
    payload = generate_latest().decode("utf-8")
    assert "devlens_analysis_stage_duration_seconds_bucket" in payload
    assert 'stage="parsing"' in payload
    assert 'status="success"' in payload


def test_trace_span_context_executes() -> None:
    with telemetry.trace_span("worker.test", trace_id="trace-1", step="unit"):
        assert True


def test_start_metrics_server_is_tolerant_for_ephemeral_port() -> None:
    telemetry.start_metrics_server(0)
