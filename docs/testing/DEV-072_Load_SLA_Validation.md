# DEV-072 Load and SLA Validation

This document defines the repeatable load/SLA validation procedure for analysis and chat.

## 1. Ticket Scope

- Ticket: `DEV-072`
- Targets from SRD v1.1:
- Analysis benchmark target: `< 3 minutes` (`< 180s`) for 50k LOC scenario.
- Chat startup target: first streamed token `< 1 second` (`< 1000ms`) under expected load.

## 2. Prerequisites

- Docker stack healthy (`backend`, `worker`, `postgres`, `redis`, `qdrant`).
- Benchmark repository accessible from GitHub.
- Valid bearer token for an authenticated user.
- Worker queues consuming analysis jobs.

## 3. Benchmark Command

Run:

```powershell
./scripts/sla-benchmark.ps1 `
  -BaseUrl "http://localhost:8000/api/v1" `
  -AccessToken "<ACCESS_TOKEN>" `
  -RepoUrl "https://github.com/owner/repo" `
  -Runs 5 `
  -PollIntervalSec 2 `
  -ChatPrompt "Where is authentication refresh handled?"
```

Outputs:
- `artifacts/load/<run_id>/sla-report.json`
- `artifacts/load/<run_id>/sla-runs.csv`

Captured metrics:
- Per run:
- analysis duration (submit analyze to terminal `done`)
- chat first token latency (SSE `delta` first seen)
- chat stream total duration
- Aggregates:
- `analysis_p50_sec`, `analysis_p95_sec`
- `first_token_p50_ms`, `first_token_p95_ms`

## 4. Acceptance Evaluation

Pass conditions:
- `analysis_p95_sec < 180`
- `first_token_p95_ms < 1000`
- No terminal `error` events in benchmark runs.

If failing:
- Record top bottleneck stage (`cloning/parsing/embedding/analyzing`) from status payloads.
- Capture worker concurrency settings and hardware context.
- Re-run after tuning and compare before/after p95 deltas.

## 5. Report Template

Use `docs/testing/sla_results_template.md` for PR evidence and release notes.

At minimum include:
- benchmark date/time
- environment profile
- repo URL and estimated LOC
- p50/p95 metrics
- pass/fail per SLA target
- bottlenecks and next action
