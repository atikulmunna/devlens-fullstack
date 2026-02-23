# GitHub Issues Batch (DevLens v1.1)

Copy one issue block at a time into GitHub Issues.

## Issue: [DEV-001] Monorepo and service layout

**Title**
[DEV-001][P0] Monorepo and service layout

**Body Template**
```markdown
## Summary
Create `/backend`, `/frontend`, `/workers`, shared docs/scripts structure.

## Priority
P0

## Tasks
- [ ] Initialize repository structure and README stubs per service.
- [ ] Add root-level `.editorconfig`, `.gitignore`, and shared Makefile/task runner.
- [ ] Add service-local env example files.

## Acceptance Criteria
- [ ] All services boot independently in local dev.
- [ ] Project structure matches SRD sections and is documented.

## Dependencies
- None

## Labels
- P0
- DEV-001
```

## Issue: [DEV-002] Docker Compose local stack

**Title**
[DEV-002][P0] Docker Compose local stack

**Body Template**
```markdown
## Summary
Local stack for FastAPI, worker, PostgreSQL, Redis, Qdrant.

## Priority
P0

## Tasks
- [ ] Add `docker-compose.yml` with health checks.
- [ ] Add named volumes and startup order/wait strategy.
- [ ] Add one-command startup script.

## Acceptance Criteria
- [ ] `docker compose up` yields healthy services.
- [ ] Backend can connect to all dependencies without manual steps.

## Dependencies
- DEV-001

## Labels
- P0
- DEV-002
```

## Issue: [DEV-003] Configuration and secrets baseline

**Title**
[DEV-003][P0] Configuration and secrets baseline

**Body Template**
```markdown
## Summary
Centralized config loading and validation for backend/worker/frontend.

## Priority
P0

## Tasks
- [ ] Add typed settings with startup validation.
- [ ] Include required env vars from SRD v1.1.
- [ ] Fail fast on missing required secrets.

## Acceptance Criteria
- [ ] Missing required env var causes clear startup error.
- [ ] Env docs include all required keys and defaults where safe.

## Dependencies
- DEV-001

## Labels
- P0
- DEV-003
```

## Issue: [DEV-010] GitHub OAuth backend flow

**Title**
[DEV-010][P0] GitHub OAuth backend flow

**Body Template**
```markdown
## Summary
FastAPI-only OAuth initiation and callback.

## Priority
P0

## Tasks
- [ ] Implement `/auth/github` and `/auth/callback`.
- [ ] Exchange auth code with GitHub and fetch profile.
- [ ] Upsert user record.

## Acceptance Criteria
- [ ] New and returning users can log in through backend flow.
- [ ] No frontend token issuer is used.

## Dependencies
- DEV-003

## Labels
- P0
- DEV-010
```

## Issue: [DEV-011] JWT access + refresh lifecycle

**Title**
[DEV-011][P0] JWT access + refresh lifecycle

**Body Template**
```markdown
## Summary
Single auth authority with backend-issued JWT and HttpOnly refresh cookie.

## Priority
P0

## Tasks
- [ ] Implement access token issuance (`15m`) and refresh token (`7d`).
- [ ] Implement `/auth/refresh`, `/auth/logout`, `/auth/me`.
- [ ] Implement refresh token persistence and revocation logic.

## Acceptance Criteria
- [ ] Expired access token can be refreshed with valid refresh cookie.
- [ ] Logout invalidates refresh token.
- [ ] Auth middleware guards all protected routes.

## Dependencies
- DEV-010

## Labels
- P0
- DEV-011
```

## Issue: [DEV-012] CSRF and cookie security controls

**Title**
[DEV-012][P0] CSRF and cookie security controls

**Body Template**
```markdown
## Summary
Protect cookie-based auth endpoints.

## Priority
P0

## Tasks
- [ ] Enforce `Secure`, `HttpOnly`, `SameSite` strategy.
- [ ] Add CSRF protection for refresh/logout flows.
- [ ] Add origin checks for auth endpoints.

## Acceptance Criteria
- [ ] CSRF regression tests pass for refresh/logout.
- [ ] Cookies comply with production security attributes.

## Dependencies
- DEV-011

## Labels
- P0
- DEV-012
```

## Issue: [DEV-020] Analyze endpoint with idempotency

**Title**
[DEV-020][P1] Analyze endpoint with idempotency

**Body Template**
```markdown
## Summary
`POST /repos/analyze` with `Idempotency-Key`.

## Priority
P1

## Tasks
- [ ] Implement request validation and GitHub URL normalization.
- [ ] Implement idempotency lock and duplicate suppression.
- [ ] Return existing active/completed job when duplicate.

## Acceptance Criteria
- [ ] Repeat requests with same idempotency key do not create duplicate jobs.
- [ ] Response includes `job_id`, `repo_id`, `status`, `cache_hit`, `commit_sha`.

## Dependencies
- DEV-003, DEV-011

## Labels
- P1
- DEV-020
```

## Issue: [DEV-021] Repo metadata + commit resolution

**Title**
[DEV-021][P1] Repo metadata + commit resolution

**Body Template**
```markdown
## Summary
Resolve `full_name`, `default_branch`, head `commit_sha`.

## Priority
P1

## Tasks
- [ ] Query GitHub API for repo metadata.
- [ ] Persist `full_name`, `default_branch`, `latest_commit_sha`.
- [ ] Use `repo+branch+sha` cache key strategy.

## Acceptance Criteria
- [ ] Cache and dedupe logic always evaluated against latest branch head.

## Dependencies
- DEV-020

## Labels
- P1
- DEV-021
```

## Issue: [DEV-022] Parse worker with guardrails

**Title**
[DEV-022][P1] Parse worker with guardrails

**Body Template**
```markdown
## Summary
Clone/filter/chunk pipeline stage with stage timeouts.

## Priority
P1

## Tasks
- [ ] Shallow clone and enforce 60s clone timeout.
- [ ] Enforce max file and max chunk guardrails.
- [ ] Chunk source files and persist to `code_chunks`.

## Acceptance Criteria
- [ ] Oversized/over-limit repos fail with explicit error code/message.
- [ ] Parse stage emits progress events.

## Dependencies
- DEV-002, DEV-021

## Labels
- P1
- DEV-022
```

## Issue: [DEV-023] Embed worker and Qdrant indexing

**Title**
[DEV-023][P1] Embed worker and Qdrant indexing

**Body Template**
```markdown
## Summary
Generate embeddings and upsert to single Qdrant collection.

## Priority
P1

## Tasks
- [ ] Integrate embedding model (`all-MiniLM-L6-v2`).
- [ ] Upsert points with payload metadata including `repo_id`.
- [ ] Add retry with bounded backoff for transient failures.

## Acceptance Criteria
- [ ] Vectors stored in `devlens_code_chunks`.
- [ ] Upserted points are queryable with `repo_id` filters.

## Dependencies
- DEV-022

## Labels
- P1
- DEV-023
```

## Issue: [DEV-024] Analyze worker (static + summary + contributors)

**Title**
[DEV-024][P1] Analyze worker (static + summary + contributors)

**Body Template**
```markdown
## Summary
Static analysis and aggregation stage.

## Priority
P1

## Tasks
- [ ] Implement v1 analyzers for Python + TypeScript/JavaScript.
- [ ] Compute tech debt indicators and quality score inputs.
- [ ] Pull contributor stats via GitHub API.
- [ ] Generate architecture summary via LLM.

## Acceptance Criteria
- [ ] `analysis_results` populated with required dashboard fields.
- [ ] Unsupported language files degrade gracefully without job failure.

## Dependencies
- DEV-022

## Labels
- P1
- DEV-024
```

## Issue: [DEV-025] SSE job status stream

**Title**
[DEV-025][P1] SSE job status stream

**Body Template**
```markdown
## Summary
`GET /repos/{repo_id}/status` event contract.

## Priority
P1

## Tasks
- [ ] Emit `progress`, `done`, `error` events with SRD payload shape.
- [ ] Persist stage and numeric progress in `analysis_jobs`.
- [ ] Handle reconnects without duplicating terminal events.

## Acceptance Criteria
- [ ] Frontend receives stage updates in correct order.
- [ ] Error event includes machine-readable error code.

## Dependencies
- DEV-020, DEV-022, DEV-023, DEV-024

## Labels
- P1
- DEV-025
```

## Issue: [DEV-030] PostgreSQL FTS lexical retrieval

**Title**
[DEV-030][P1] PostgreSQL FTS lexical retrieval

**Body Template**
```markdown
## Summary
Replace BM25 assumption with PostgreSQL FTS implementation.

## Priority
P1

## Tasks
- [ ] Add `fts` column and GIN index on `code_chunks`.
- [ ] Populate/update `fts` during chunk writes.
- [ ] Implement ranked lexical query (`ts_rank_cd`).

## Acceptance Criteria
- [ ] Keyword queries return relevant file-path/symbol matches.
- [ ] Query latency remains within acceptable bounds for target repo size.

## Dependencies
- DEV-022

## Labels
- P1
- DEV-030
```

## Issue: [DEV-031] Hybrid retrieval with reranking

**Title**
[DEV-031][P1] Hybrid retrieval with reranking

**Body Template**
```markdown
## Summary
Dense + lexical merge and cross-encoder rerank.

## Priority
P1

## Tasks
- [ ] Implement Qdrant vector query with mandatory `repo_id` filter.
- [ ] Merge dense and lexical candidates.
- [ ] Apply reranker and select top-k context chunks.

## Acceptance Criteria
- [ ] Requests without `repo_id` filter are rejected server-side.
- [ ] Retrieval outputs are stable and deterministic for same inputs.

## Dependencies
- DEV-023, DEV-030

## Labels
- P1
- DEV-031
```

## Issue: [DEV-032] Chat session and message APIs

**Title**
[DEV-032][P1] Chat session and message APIs

**Body Template**
```markdown
## Summary
Chat lifecycle endpoints and message persistence.

## Priority
P1

## Tasks
- [ ] Implement session create/get/delete endpoints.
- [ ] Implement message endpoint with streamed assistant responses.
- [ ] Persist assistant citations in `chat_messages.source_citations`.

## Acceptance Criteria
- [ ] Conversation history is resumable by session.
- [ ] Every assistant response contains citations or explicit no-citation flag.

## Dependencies
- DEV-011, DEV-031

## Labels
- P1
- DEV-032
```

## Issue: [DEV-033] Citation formatting and file anchors

**Title**
[DEV-033][P1] Citation formatting and file anchors

**Body Template**
```markdown
## Summary
Output clickable `file_path + line range` citations.

## Priority
P1

## Tasks
- [ ] Map chunks to source file and line ranges.
- [ ] Return citation schema consistent across chat and dashboard.
- [ ] Add backend validation for citation payload integrity.

## Acceptance Criteria
- [ ] Citations resolve to existing files/line intervals in analyzed repo snapshot.

## Dependencies
- DEV-032

## Labels
- P1
- DEV-033
```

## Issue: [DEV-040] Frontend app shell and route scaffolding

**Title**
[DEV-040][P1] Frontend app shell and route scaffolding

**Body Template**
```markdown
## Summary
Next.js app router pages from SRD.

## Priority
P1

## Tasks
- [ ] Implement `/`, `/analyze`, `/dashboard/[repoId]`, `/dashboard/[repoId]/chat`, `/dashboard/[repoId]/files`, `/profile`, `/share/[token]`.
- [ ] Add global error/loading states.

## Acceptance Criteria
- [ ] All routes render with basic skeletons and no runtime errors.

## Dependencies
- DEV-001

## Labels
- P1
- DEV-040
```

## Issue: [DEV-041] Analyze flow UI + SSE tracker

**Title**
[DEV-041][P1] Analyze flow UI + SSE tracker

**Body Template**
```markdown
## Summary
URL submission, progress visualization, redirect to dashboard.

## Priority
P1

## Tasks
- [ ] Build repo input form with validation feedback.
- [ ] Consume SSE status endpoint and render stage timeline.
- [ ] Handle cache hit and failed job states.

## Acceptance Criteria
- [ ] User can submit repo URL and observe live stage updates.
- [ ] UI handles reconnect and terminal errors cleanly.

## Dependencies
- DEV-020, DEV-025, DEV-040

## Labels
- P1
- DEV-041
```

## Issue: [DEV-042] Dashboard core panels

**Title**
[DEV-042][P1] Dashboard core panels

**Body Template**
```markdown
## Summary
Overview, architecture summary, tech debt, quality score, file explorer.

## Priority
P1

## Tasks
- [ ] Wire REST data fetching with query caching.
- [ ] Implement panel components with empty/error/loading states.
- [ ] Add contributor analytics panel.

## Acceptance Criteria
- [ ] Dashboard renders all core v1 panels with real backend data.

## Dependencies
- DEV-024, DEV-040

## Labels
- P1
- DEV-042
```

## Issue: [DEV-043] Chat interface with streaming

**Title**
[DEV-043][P1] Chat interface with streaming

**Body Template**
```markdown
## Summary
Session list, message timeline, streamed answer rendering, citations.

## Priority
P1

## Tasks
- [ ] Implement chat container and message components.
- [ ] Render code snippets with syntax highlighting.
- [ ] Add suggested question chips endpoint integration.

## Acceptance Criteria
- [ ] Streaming starts within 1 second under normal conditions.
- [ ] Citations are visible and navigable.

## Dependencies
- DEV-032, DEV-033, DEV-040

## Labels
- P1
- DEV-043
```

## Issue: [DEV-044] Export and public share

**Title**
[DEV-044][P2] Export and public share

**Body Template**
```markdown
## Summary
Export menu and share-link UX.

## Priority
P2

## Tasks
- [ ] Add markdown/html/pdf export actions.
- [ ] Add share link generation and revoke controls.
- [ ] Add public share page data fetch and guard rails.

## Acceptance Criteria
- [ ] Generated links respect token TTL and revocation.

## Dependencies
- DEV-060, DEV-061, DEV-040

## Labels
- P2
- DEV-044
```

## Issue: [DEV-050] Database migrations for v1.1 schema

**Title**
[DEV-050][P0] Database migrations for v1.1 schema

**Body Template**
```markdown
## Summary
Implement SRD table updates and indexes.

## Priority
P0

## Tasks
- [ ] Create Alembic migrations for added columns (`full_name`, `default_branch`, `latest_commit_sha`, `idempotency_key`, `commit_sha`, `cache_key`, `fts`).
- [ ] Add required indexes.
- [ ] Backfill defaults for existing rows if any.

## Acceptance Criteria
- [ ] Fresh and upgrade migrations both succeed.
- [ ] Query plans use new indexes for hot paths.

## Dependencies
- DEV-003

## Labels
- P0
- DEV-050
```

## Issue: [DEV-051] API error envelope standardization

**Title**
[DEV-051][P1] API error envelope standardization

**Body Template**
```markdown
## Summary
Uniform error response shape across endpoints.

## Priority
P1

## Tasks
- [ ] Add global exception handlers.
- [ ] Map validation/auth/limit/internal errors to standard codes.
- [ ] Update OpenAPI examples.

## Acceptance Criteria
- [ ] All endpoints return `{ error: { code, message, details } }` on failures.

## Dependencies
- DEV-020

## Labels
- P1
- DEV-051
```

## Issue: [DEV-052] OpenAPI and SSE contract documentation

**Title**
[DEV-052][P1] OpenAPI and SSE contract documentation

**Body Template**
```markdown
## Summary
Contract-level documentation parity with SRD.

## Priority
P1

## Tasks
- [ ] Add request/response examples for analyze/chat/auth/export.
- [ ] Document SSE event schemas and reconnection behavior.
- [ ] Version docs with SRD v1.1 references.

## Acceptance Criteria
- [ ] Frontend can implement against API docs without backend source reading.

## Dependencies
- DEV-020, DEV-025, DEV-032

## Labels
- P1
- DEV-052
```

## Issue: [DEV-060] Signed share token service

**Title**
[DEV-060][P0] Signed share token service

**Body Template**
```markdown
## Summary
Create signed share links with TTL and revocation.

## Priority
P0

## Tasks
- [ ] Implement token generation and verification.
- [ ] Store revoked tokens and expiry metadata.
- [ ] Ensure shared payload excludes private user data.

## Acceptance Criteria
- [ ] Expired/revoked links return deterministic auth error.

## Dependencies
- DEV-011

## Labels
- P0
- DEV-060
```

## Issue: [DEV-061] Rate limiting and abuse controls

**Title**
[DEV-061][P0] Rate limiting and abuse controls

**Body Template**
```markdown
## Summary
Guest/auth quotas and anti-abuse for analysis/chat.

## Priority
P0

## Tasks
- [ ] Add Redis-backed rate limiter middleware.
- [ ] Enforce guest/auth request ceilings from SRD.
- [ ] Add response headers for remaining quota.

## Acceptance Criteria
- [ ] Limits enforce correctly per identity type.

## Dependencies
- DEV-002, DEV-011

## Labels
- P0
- DEV-061
```

## Issue: [DEV-062] Retry, DLQ, and resumability

**Title**
[DEV-062][P1] Retry, DLQ, and resumability

**Body Template**
```markdown
## Summary
Worker reliability controls.

## Priority
P1

## Tasks
- [ ] Add bounded retries with exponential backoff.
- [ ] Add dead-letter queue handling/reporting.
- [ ] Add stage checkpointing for resume.

## Acceptance Criteria
- [ ] Recoverable failures retry automatically.
- [ ] Non-recoverable failures land in DLQ with reason.

## Dependencies
- DEV-022, DEV-023, DEV-024

## Labels
- P1
- DEV-062
```

## Issue: [DEV-063] Metrics and tracing baseline

**Title**
[DEV-063][P1] Metrics and tracing baseline

**Body Template**
```markdown
## Summary
Observability for SLOs and pipeline debugging.

## Priority
P1

## Tasks
- [ ] Emit stage duration metrics and endpoint latency.
- [ ] Emit SSE start latency metric.
- [ ] Add tracing spans across API and workers.

## Acceptance Criteria
- [ ] Dashboards show p95 latency and analysis stage timings.

## Dependencies
- DEV-022, DEV-023, DEV-024, DEV-025

## Labels
- P1
- DEV-063
```

## Issue: [DEV-070] Backend unit/integration test suite

**Title**
[DEV-070][P0] Backend unit/integration test suite

**Body Template**
```markdown
## Summary
Reach and maintain >70% backend coverage.

## Priority
P0

## Tasks
- [ ] Add tests for auth lifecycle, analyze idempotency, retrieval, and SSE behavior.
- [ ] Add service mocks for GitHub, LLM, and vector DB boundaries.
- [ ] Add migration and repository-layer tests.

## Acceptance Criteria
- [ ] CI reports backend coverage >= 70%.

## Dependencies
- DEV-050, DEV-011, DEV-020, DEV-031

## Labels
- P0
- DEV-070
```

## Issue: [DEV-071] Golden repo relevance evaluation

**Title**
[DEV-071][P1] Golden repo relevance evaluation

**Body Template**
```markdown
## Summary
Build fixed evaluation set for chat relevance/citations.

## Priority
P1

## Tasks
- [ ] Select representative public repos and question set.
- [ ] Define scoring rubric for answer relevance and citation correctness.
- [ ] Track baseline and post-change scores.

## Acceptance Criteria
- [ ] Manual eval process is repeatable and documented.

## Dependencies
- DEV-031, DEV-032, DEV-033

## Labels
- P1
- DEV-071
```

## Issue: [DEV-072] Load and SLA validation

**Title**
[DEV-072][P1] Load and SLA validation

**Body Template**
```markdown
## Summary
Verify 50k LOC analysis SLA and chat startup latency.

## Priority
P1

## Tasks
- [ ] Add load scenarios for analyze and chat workflows.
- [ ] Measure stage-level durations and tune concurrency.
- [ ] Document achieved p95s and bottlenecks.

## Acceptance Criteria
- [ ] Evidence of <3 minute analysis target for defined benchmark set.
- [ ] Chat stream first token target met under expected load.

## Dependencies
- DEV-062, DEV-063

## Labels
- P1
- DEV-072
```

## Issue: [DEV-073] CI/CD release pipeline

**Title**
[DEV-073][P1] CI/CD release pipeline

**Body Template**
```markdown
## Summary
Lint/test/build/deploy automation.

## Priority
P1

## Tasks
- [ ] Implement GitHub Actions pipeline per SRD.
- [ ] Add required checks to protect main branch.
- [ ] Add deploy notifications and rollback notes.

## Acceptance Criteria
- [ ] Merge to main triggers full pipeline and deployment.

## Dependencies
- DEV-070

## Labels
- P1
- DEV-073
```

## Issue: [DEV-080] Dependency graph panel

**Title**
[DEV-080][P3] Dependency graph panel

**Body Template**
```markdown
## Summary
React Flow-based module import graph.

## Priority
P3

## Tasks
- [ ] Define implementation tasks

## Entry Criteria
- [ ] Core dashboard and chat are stable in production-like environment.

## Acceptance Criteria
- [ ] Meets agreed requirements

## Dependencies
- None

## Labels
- P3
- DEV-080
```

## Issue: [DEV-081] Programmatic API key management

**Title**
[DEV-081][P3] Programmatic API key management

**Body Template**
```markdown
## Summary
API key issue/rotate/revoke and scoped usage.

## Priority
P3

## Tasks
- [ ] Define implementation tasks

## Entry Criteria
- [ ] Core auth and rate limit controls proven stable.

## Acceptance Criteria
- [ ] Meets agreed requirements

## Dependencies
- None

## Labels
- P3
- DEV-081
```

