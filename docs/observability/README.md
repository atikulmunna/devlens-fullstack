# DEV-063 Observability Dashboard Baseline

This folder provides dashboard evidence for the DEV-063 acceptance criterion:
"Dashboards show p95 latency and analysis stage timings."

## Metrics Sources

- Backend Prometheus endpoint: `GET /metrics`
- Worker Prometheus endpoint: `http://<worker-host>:9101/metrics`

## Dashboard Artifact

- `grafana_devlens_baseline.json`
  - `API p95 latency (seconds)` from `devlens_http_request_duration_seconds`
  - `SSE startup p95 latency (seconds)` from `devlens_sse_startup_latency_seconds`
  - `Worker stage p95 durations (seconds)` from `devlens_analysis_stage_duration_seconds`
  - `Stage throughput by status` from worker stage histograms

## PromQL snippets

- API p95:
  - `histogram_quantile(0.95, sum by (le, method, path) (rate(devlens_http_request_duration_seconds_bucket[5m])))`
- SSE startup p95:
  - `histogram_quantile(0.95, sum by (le, endpoint) (rate(devlens_sse_startup_latency_seconds_bucket[5m])))`
- Worker stage p95:
  - `histogram_quantile(0.95, sum by (le, stage, status) (rate(devlens_analysis_stage_duration_seconds_bucket[5m])))`
