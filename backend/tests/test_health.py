from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    response = client.get('/health')
    assert response.status_code == 200
    assert response.headers.get('x-trace-id')
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['service'] == 'backend'


def test_trace_id_header_propagates_incoming_value(client: TestClient) -> None:
    response = client.get('/health', headers={'x-trace-id': 'trace-from-client'})
    assert response.status_code == 200
    assert response.headers.get('x-trace-id') == 'trace-from-client'


def test_health_deps_endpoint_shape(client: TestClient) -> None:
    response = client.get('/health/deps')
    assert response.status_code == 200
    payload = response.json()
    for key in ('redis', 'postgres', 'qdrant', 'all_healthy'):
        assert key in payload


def test_metrics_endpoint_exposes_core_metrics(client: TestClient) -> None:
    # Prime at least one request metric sample.
    client.get('/health')

    response = client.get('/metrics')
    assert response.status_code == 200
    assert 'devlens_http_request_duration_seconds' in response.text
    assert 'devlens_sse_startup_latency_seconds' in response.text
