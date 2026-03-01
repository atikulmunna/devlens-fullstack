from prometheus_client import generate_latest

import telemetry


def test_record_stage_duration_emits_metric_sample() -> None:
    telemetry.record_stage_duration("parsing", "success", 0.25)
    payload = generate_latest().decode("utf-8")
    assert "devlens_analysis_stage_duration_seconds_bucket" in payload
    assert 'stage="parsing"' in payload
    assert 'status="success"' in payload


def test_llm_provider_and_fallback_metrics_emit_samples() -> None:
    telemetry.record_llm_provider_attempt("openrouter", "error", "LLM_PROVIDER_HTTP_ERROR")
    telemetry.record_llm_fallback("openrouter", "groq", "primary_failed")
    payload = generate_latest().decode("utf-8")
    assert "devlens_llm_provider_attempts_total" in payload
    assert 'provider="openrouter"' in payload
    assert "devlens_llm_fallback_total" in payload
    assert 'fallback_provider="groq"' in payload


def test_trace_span_context_executes() -> None:
    with telemetry.trace_span("worker.test", trace_id="trace-1", step="unit"):
        assert True


def test_start_metrics_server_is_tolerant_for_ephemeral_port() -> None:
    telemetry.start_metrics_server(0)
