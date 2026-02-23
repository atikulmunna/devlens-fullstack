# Worker Service

Background workers for DevLens async jobs.

## Local

1. Copy `.env.example` to `.env`.
2. Install dependencies from `requirements.txt`.
3. Run `python worker.py`.
4. Run tests with `pytest -q`.

## Observability

- Worker stage duration histogram: `devlens_analysis_stage_duration_seconds{stage,status}`.
- Metrics server starts on `WORKER_METRICS_PORT` (default `9101`).
- Worker logs include trace span start/end entries with `trace_id` per job stage.
