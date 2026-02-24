# DevLens v1.1 Release QA

- Date: 2026-02-25
- Commit: `b677411`
- Tester: Codex + Munna
- Environment: Local Docker Compose (Windows host, containers on Docker Desktop)

## Prerequisites

- Docker Desktop running
- Repo on `main`
- Services started and healthy

## Startup and Health

- [x] `./scripts/dev-up.ps1`
- [x] `./scripts/db-migrate.ps1`
- [x] `GET http://localhost:8000/health` returns `200`
- [x] `GET http://localhost:8000/health/deps` returns `all_healthy=true`
- [x] `GET http://localhost:3000/health` returns `200`

Evidence:
- `backend_health_status=200`
- `backend_deps_status=200` with `all_healthy=true`
- `frontend_health_status=200`

## Auth and Session

- [x] Backend auth lifecycle validated with seeded refresh token + CSRF headers
- [x] `/api/v1/auth/refresh` returns access token with valid CSRF
- [x] `/api/v1/auth/me` returns current user with bearer token
- [x] `/api/v1/auth/logout` invalidates refresh token and clears cookie

Evidence:
- `auth_refresh_status=200`
- `auth_me_status=200` user `qa-user`
- `auth_logout_status=204`
- `auth_refresh_after_logout_status=401`
- QA artifact: `artifacts/qa/release-qa-20260225-011739.json`

## Analyze and Pipeline

- [x] `POST /api/v1/repos/analyze` returns `job_id`, `repo_id`, `status`, `cache_hit`, `commit_sha`
- [x] `GET /api/v1/repos/{repo_id}/status` reaches terminal event
- [x] `GET /api/v1/repos/{repo_id}/dashboard` returns core analysis payload

Evidence:
- `analyze_status=200`, `job_id=be9b8388-a61b-40c3-8a5b-5f0bea73eb8f`
- `status_terminal_event=done`, `status_terminal_progress=100`
- `dashboard_status=200`, `dashboard_has_analysis=true`
- `repo_id=56ebc0e6-8a25-4e9b-8c01-fb18f177c3f6`

## Retrieval and Chat

- [x] `GET /api/v1/repos/{repo_id}/search/lexical` returns ranked results
- [x] `GET /api/v1/repos/{repo_id}/search/hybrid` returns merged/reranked results
- [x] `POST /api/v1/chat/sessions` creates session
- [x] `POST /api/v1/chat/sessions/{id}/message` streams response and citations
- [x] `GET /api/v1/chat/sessions/{id}` returns resumable history

Evidence:
- `lexical_status=200`, `lexical_total=5`
- `hybrid_status=200`, `hybrid_total=5`
- `chat_session_create_status=200`
- `chat_message_status=200`, `chat_stream_has_done=true`
- `chat_get_status=200`, `chat_message_count=2`

## Share and Export

- [x] `POST /api/v1/export/{repo_id}/share` creates signed share link
- [x] `GET /api/v1/share/{token}` resolves public payload
- [x] `DELETE /api/v1/export/share/{share_id}` revokes link
- [x] Post-revoke token access returns deterministic auth failure

Evidence:
- `share_create_status=200`
- `share_get_status=200`
- `share_revoke_status=204`
- `share_get_after_revoke_status=401`

## API Keys

- [x] `POST /api/v1/auth/api-keys` issues key once
- [x] `GET /api/v1/auth/api-keys` lists active keys
- [x] `DELETE /api/v1/auth/api-keys/{id}` revokes key

Evidence:
- `api_key_create_status=200`
- `api_key_list_status=200`
- `api_key_revoke_status=204`

## Observability

- [x] `GET /metrics` exposes backend latency + SSE startup histograms
- [x] Worker metrics endpoint exposes stage duration histogram (validated from worker container)
- [x] Dashboard artifact present at `docs/observability/grafana_devlens_baseline.json`

Evidence:
- `metrics_backend_status=200`
- `metrics_backend_has_http=true`
- `metrics_backend_has_sse=true` (after SSE probe)
- `metrics_worker_status=200`
- `metrics_worker_has_stage=true`

## Test Suites

- [x] `./scripts/test-backend.ps1` pass
- [x] `./scripts/test-worker.ps1` pass

Evidence:
- Backend coverage: `88.01%` (threshold `>=70%`)
- Worker tests: passed (`26` tests)

## Final Verdict

- [x] PASS for release
- [ ] FAIL for release

Notes:
- QA evidence artifact: `artifacts/qa/release-qa-20260225-011739.json`
- Frontend route smoke all returned `200`: `/`, `/analyze`, `/dashboard/{repo}`, `/dashboard/{repo}/chat`, `/dashboard/{repo}/files`, `/profile`, `/share/demo-token`
