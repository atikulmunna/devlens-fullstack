# DevLens v1.1 Implementation Checklist

Source of truth: `DevLens_SRD.md` (Version 1.1, February 23, 2026)

## Usage

- Create one issue per ticket ID.
- Keep acceptance criteria unchanged unless scope is explicitly re-approved.
- Mark blocker tickets first (`P0`) before feature tickets.

## Priority Legend

- `P0`: Blocks core architecture or security
- `P1`: Core v1 product capability
- `P2`: Important polish and resilience
- `P3`: v1.1 follow-up

## Epic A: Platform Foundation

### DEV-001 (`P0`) Monorepo and service layout
- Scope: Create `/backend`, `/frontend`, `/workers`, shared docs/scripts structure.
- Tasks:
- [ ] Initialize repository structure and README stubs per service.
- [ ] Add root-level `.editorconfig`, `.gitignore`, and shared Makefile/task runner.
- [ ] Add service-local env example files.
- Acceptance criteria:
- [ ] All services boot independently in local dev.
- [ ] Project structure matches SRD sections and is documented.
- Dependencies: None

### DEV-002 (`P0`) Docker Compose local stack
- Scope: Local stack for FastAPI, worker, PostgreSQL, Redis, Qdrant.
- Tasks:
- [ ] Add `docker-compose.yml` with health checks.
- [ ] Add named volumes and startup order/wait strategy.
- [ ] Add one-command startup script.
- Acceptance criteria:
- [ ] `docker compose up` yields healthy services.
- [ ] Backend can connect to all dependencies without manual steps.
- Dependencies: DEV-001

### DEV-003 (`P0`) Configuration and secrets baseline
- Scope: Centralized config loading and validation for backend/worker/frontend.
- Tasks:
- [ ] Add typed settings with startup validation.
- [ ] Include required env vars from SRD v1.1.
- [ ] Fail fast on missing required secrets.
- Acceptance criteria:
- [ ] Missing required env var causes clear startup error.
- [ ] Env docs include all required keys and defaults where safe.
- Dependencies: DEV-001

## Epic B: Authentication and Session Architecture

### DEV-010 (`P0`) GitHub OAuth backend flow
- Scope: FastAPI-only OAuth initiation and callback.
- Tasks:
- [ ] Implement `/auth/github` and `/auth/callback`.
- [ ] Exchange auth code with GitHub and fetch profile.
- [ ] Upsert user record.
- Acceptance criteria:
- [ ] New and returning users can log in through backend flow.
- [ ] No frontend token issuer is used.
- Dependencies: DEV-003

### DEV-011 (`P0`) JWT access + refresh lifecycle
- Scope: Single auth authority with backend-issued JWT and HttpOnly refresh cookie.
- Tasks:
- [ ] Implement access token issuance (`15m`) and refresh token (`7d`).
- [ ] Implement `/auth/refresh`, `/auth/logout`, `/auth/me`.
- [ ] Implement refresh token persistence and revocation logic.
- Acceptance criteria:
- [ ] Expired access token can be refreshed with valid refresh cookie.
- [ ] Logout invalidates refresh token.
- [ ] Auth middleware guards all protected routes.
- Dependencies: DEV-010

### DEV-012 (`P0`) CSRF and cookie security controls
- Scope: Protect cookie-based auth endpoints.
- Tasks:
- [ ] Enforce `Secure`, `HttpOnly`, `SameSite` strategy.
- [ ] Add CSRF protection for refresh/logout flows.
- [ ] Add origin checks for auth endpoints.
- Acceptance criteria:
- [ ] CSRF regression tests pass for refresh/logout.
- [ ] Cookies comply with production security attributes.
- Dependencies: DEV-011

## Epic C: Repository Analysis Pipeline

### DEV-020 (`P1`) Analyze endpoint with idempotency
- Scope: `POST /repos/analyze` with `Idempotency-Key`.
- Tasks:
- [ ] Implement request validation and GitHub URL normalization.
- [ ] Implement idempotency lock and duplicate suppression.
- [ ] Return existing active/completed job when duplicate.
- Acceptance criteria:
- [ ] Repeat requests with same idempotency key do not create duplicate jobs.
- [ ] Response includes `job_id`, `repo_id`, `status`, `cache_hit`, `commit_sha`.
- Dependencies: DEV-003, DEV-011

### DEV-021 (`P1`) Repo metadata + commit resolution
- Scope: Resolve `full_name`, `default_branch`, head `commit_sha`.
- Tasks:
- [ ] Query GitHub API for repo metadata.
- [ ] Persist `full_name`, `default_branch`, `latest_commit_sha`.
- [ ] Use `repo+branch+sha` cache key strategy.
- Acceptance criteria:
- [ ] Cache and dedupe logic always evaluated against latest branch head.
- Dependencies: DEV-020

### DEV-022 (`P1`) Parse worker with guardrails
- Scope: Clone/filter/chunk pipeline stage with stage timeouts.
- Tasks:
- [ ] Shallow clone and enforce 60s clone timeout.
- [ ] Enforce max file and max chunk guardrails.
- [ ] Chunk source files and persist to `code_chunks`.
- Acceptance criteria:
- [ ] Oversized/over-limit repos fail with explicit error code/message.
- [ ] Parse stage emits progress events.
- Dependencies: DEV-002, DEV-021

### DEV-023 (`P1`) Embed worker and Qdrant indexing
- Scope: Generate embeddings and upsert to single Qdrant collection.
- Tasks:
- [ ] Integrate embedding model (`all-MiniLM-L6-v2`).
- [ ] Upsert points with payload metadata including `repo_id`.
- [ ] Add retry with bounded backoff for transient failures.
- Acceptance criteria:
- [ ] Vectors stored in `devlens_code_chunks`.
- [ ] Upserted points are queryable with `repo_id` filters.
- Dependencies: DEV-022

### DEV-024 (`P1`) Analyze worker (static + summary + contributors)
- Scope: Static analysis and aggregation stage.
- Tasks:
- [ ] Implement v1 analyzers for Python + TypeScript/JavaScript.
- [ ] Compute tech debt indicators and quality score inputs.
- [ ] Pull contributor stats via GitHub API.
- [ ] Generate architecture summary via LLM.
- Acceptance criteria:
- [ ] `analysis_results` populated with required dashboard fields.
- [ ] Unsupported language files degrade gracefully without job failure.
- Dependencies: DEV-022

### DEV-025 (`P1`) SSE job status stream
- Scope: `GET /repos/{repo_id}/status` event contract.
- Tasks:
- [ ] Emit `progress`, `done`, `error` events with SRD payload shape.
- [ ] Persist stage and numeric progress in `analysis_jobs`.
- [ ] Handle reconnects without duplicating terminal events.
- Acceptance criteria:
- [ ] Frontend receives stage updates in correct order.
- [ ] Error event includes machine-readable error code.
- Dependencies: DEV-020, DEV-022, DEV-023, DEV-024

## Epic D: Retrieval and Chat

### DEV-030 (`P1`) PostgreSQL FTS lexical retrieval
- Scope: Replace BM25 assumption with PostgreSQL FTS implementation.
- Tasks:
- [ ] Add `fts` column and GIN index on `code_chunks`.
- [ ] Populate/update `fts` during chunk writes.
- [ ] Implement ranked lexical query (`ts_rank_cd`).
- Acceptance criteria:
- [ ] Keyword queries return relevant file-path/symbol matches.
- [ ] Query latency remains within acceptable bounds for target repo size.
- Dependencies: DEV-022

### DEV-031 (`P1`) Hybrid retrieval with reranking
- Scope: Dense + lexical merge and cross-encoder rerank.
- Tasks:
- [ ] Implement Qdrant vector query with mandatory `repo_id` filter.
- [ ] Merge dense and lexical candidates.
- [ ] Apply reranker and select top-k context chunks.
- Acceptance criteria:
- [ ] Requests without `repo_id` filter are rejected server-side.
- [ ] Retrieval outputs are stable and deterministic for same inputs.
- Dependencies: DEV-023, DEV-030

### DEV-032 (`P1`) Chat session and message APIs
- Scope: Chat lifecycle endpoints and message persistence.
- Tasks:
- [ ] Implement session create/get/delete endpoints.
- [ ] Implement message endpoint with streamed assistant responses.
- [ ] Persist assistant citations in `chat_messages.source_citations`.
- Acceptance criteria:
- [ ] Conversation history is resumable by session.
- [ ] Every assistant response contains citations or explicit no-citation flag.
- Dependencies: DEV-011, DEV-031

### DEV-033 (`P1`) Citation formatting and file anchors
- Scope: Output clickable `file_path + line range` citations.
- Tasks:
- [ ] Map chunks to source file and line ranges.
- [ ] Return citation schema consistent across chat and dashboard.
- [ ] Add backend validation for citation payload integrity.
- Acceptance criteria:
- [ ] Citations resolve to existing files/line intervals in analyzed repo snapshot.
- Dependencies: DEV-032

## Epic E: Frontend Delivery (Core v1)

### DEV-040 (`P1`) Frontend app shell and route scaffolding
- Scope: Frontend route shell pages from SRD (framework-agnostic runtime).
- Tasks:
- [ ] Implement `/`, `/analyze`, `/dashboard/[repoId]`, `/dashboard/[repoId]/chat`, `/dashboard/[repoId]/files`, `/profile`, `/share/[token]`.
- [ ] Add global error/loading states.
- Acceptance criteria:
- [ ] All routes render with basic skeletons and no runtime errors.
- Dependencies: DEV-001

### DEV-041 (`P1`) Analyze flow UI + SSE tracker
- Scope: URL submission, progress visualization, redirect to dashboard.
- Tasks:
- [ ] Build repo input form with validation feedback.
- [ ] Consume SSE status endpoint and render stage timeline.
- [ ] Handle cache hit and failed job states.
- Acceptance criteria:
- [ ] User can submit repo URL and observe live stage updates.
- [ ] UI handles reconnect and terminal errors cleanly.
- Dependencies: DEV-020, DEV-025, DEV-040

### DEV-042 (`P1`) Dashboard core panels
- Scope: Overview, architecture summary, tech debt, quality score, file explorer.
- Tasks:
- [ ] Wire REST data fetching with query caching.
- [ ] Implement panel components with empty/error/loading states.
- [ ] Add contributor analytics panel.
- Acceptance criteria:
- [ ] Dashboard renders all core v1 panels with real backend data.
- Dependencies: DEV-024, DEV-040

### DEV-043 (`P1`) Chat interface with streaming
- Scope: Session list, message timeline, streamed answer rendering, citations.
- Tasks:
- [ ] Implement chat container and message components.
- [ ] Render code snippets with syntax highlighting.
- [ ] Add suggested question chips endpoint integration.
- Acceptance criteria:
- [ ] Streaming starts within 1 second under normal conditions.
- [ ] Citations are visible and navigable.
- Dependencies: DEV-032, DEV-033, DEV-040

### DEV-044 (`P2`) Export and public share
- Scope: Export menu and share-link UX.
- Tasks:
- [ ] Add markdown/html/pdf export actions.
- [ ] Add share link generation and revoke controls.
- [ ] Add public share page data fetch and guard rails.
- Acceptance criteria:
- [ ] Generated links respect token TTL and revocation.
- Dependencies: DEV-060, DEV-061, DEV-040

## Epic F: Data and Contract Hardening

### DEV-050 (`P0`) Database migrations for v1.1 schema
- Scope: Implement SRD table updates and indexes.
- Tasks:
- [ ] Create Alembic migrations for added columns (`full_name`, `default_branch`, `latest_commit_sha`, `idempotency_key`, `commit_sha`, `cache_key`, `fts`).
- [ ] Add required indexes.
- [ ] Backfill defaults for existing rows if any.
- Acceptance criteria:
- [ ] Fresh and upgrade migrations both succeed.
- [ ] Query plans use new indexes for hot paths.
- Dependencies: DEV-003

### DEV-051 (`P1`) API error envelope standardization
- Scope: Uniform error response shape across endpoints.
- Tasks:
- [ ] Add global exception handlers.
- [ ] Map validation/auth/limit/internal errors to standard codes.
- [ ] Update OpenAPI examples.
- Acceptance criteria:
- [ ] All endpoints return `{ error: { code, message, details } }` on failures.
- Dependencies: DEV-020

### DEV-052 (`P1`) OpenAPI and SSE contract documentation
- Scope: Contract-level documentation parity with SRD.
- Tasks:
- [ ] Add request/response examples for analyze/chat/auth/export.
- [ ] Document SSE event schemas and reconnection behavior.
- [ ] Version docs with SRD v1.1 references.
- Acceptance criteria:
- [ ] Frontend can implement against API docs without backend source reading.
- Dependencies: DEV-020, DEV-025, DEV-032

## Epic G: Security, Reliability, Observability

### DEV-060 (`P0`) Signed share token service
- Scope: Create signed share links with TTL and revocation.
- Tasks:
- [ ] Implement token generation and verification.
- [ ] Store revoked tokens and expiry metadata.
- [ ] Ensure shared payload excludes private user data.
- Acceptance criteria:
- [ ] Expired/revoked links return deterministic auth error.
- Dependencies: DEV-011

### DEV-061 (`P0`) Rate limiting and abuse controls
- Scope: Guest/auth quotas and anti-abuse for analysis/chat.
- Tasks:
- [ ] Add Redis-backed rate limiter middleware.
- [ ] Enforce guest/auth request ceilings from SRD.
- [ ] Add response headers for remaining quota.
- Acceptance criteria:
- [ ] Limits enforce correctly per identity type.
- Dependencies: DEV-002, DEV-011

### DEV-062 (`P1`) Retry, DLQ, and resumability
- Scope: Worker reliability controls.
- Tasks:
- [ ] Add bounded retries with exponential backoff.
- [ ] Add dead-letter queue handling/reporting.
- [ ] Add stage checkpointing for resume.
- Acceptance criteria:
- [ ] Recoverable failures retry automatically.
- [ ] Non-recoverable failures land in DLQ with reason.
- Dependencies: DEV-022, DEV-023, DEV-024

### DEV-063 (`P1`) Metrics and tracing baseline
- Scope: Observability for SLOs and pipeline debugging.
- Tasks:
- [ ] Emit stage duration metrics and endpoint latency.
- [ ] Emit SSE start latency metric.
- [ ] Add tracing spans across API and workers.
- Acceptance criteria:
- [ ] Dashboards show p95 latency and analysis stage timings.
- Dependencies: DEV-022, DEV-023, DEV-024, DEV-025

## Epic H: Testing and Release

### DEV-070 (`P0`) Backend unit/integration test suite
- Scope: Reach and maintain >70% backend coverage.
- Tasks:
- [ ] Add tests for auth lifecycle, analyze idempotency, retrieval, and SSE behavior.
- [ ] Add service mocks for GitHub, LLM, and vector DB boundaries.
- [ ] Add migration and repository-layer tests.
- Acceptance criteria:
- [ ] CI reports backend coverage >= 70%.
- Dependencies: DEV-050, DEV-011, DEV-020, DEV-031

### DEV-071 (`P1`) Golden repo relevance evaluation
- Scope: Build fixed evaluation set for chat relevance/citations.
- Tasks:
- [ ] Select representative public repos and question set.
- [ ] Define scoring rubric for answer relevance and citation correctness.
- [ ] Track baseline and post-change scores.
- Acceptance criteria:
- [ ] Manual eval process is repeatable and documented.
- Dependencies: DEV-031, DEV-032, DEV-033

### DEV-072 (`P1`) Load and SLA validation
- Scope: Verify 50k LOC analysis SLA and chat startup latency.
- Tasks:
- [ ] Add load scenarios for analyze and chat workflows.
- [ ] Measure stage-level durations and tune concurrency.
- [ ] Document achieved p95s and bottlenecks.
- Acceptance criteria:
- [ ] Evidence of <3 minute analysis target for defined benchmark set.
- [ ] Chat stream first token target met under expected load.
- Dependencies: DEV-062, DEV-063

### DEV-073 (`P1`) CI/CD release pipeline
- Scope: Lint/test/build/deploy automation.
- Tasks:
- [ ] Implement GitHub Actions pipeline per SRD.
- [ ] Add required checks to protect main branch.
- [ ] Add deploy notifications and rollback notes.
- Acceptance criteria:
- [ ] Merge to main triggers full pipeline and deployment.
- Dependencies: DEV-070

## v1.1 Deferred Backlog (Create but do not block v1 launch)

### DEV-080 (`P3`) Dependency graph panel
- Scope: React Flow-based module import graph.
- Entry criteria:
- [ ] Core dashboard and chat are stable in production-like environment.

### DEV-081 (`P3`) Programmatic API key management
- Scope: API key issue/rotate/revoke and scoped usage.
- Entry criteria:
- [ ] Core auth and rate limit controls proven stable.

## Definition of Done (Global)

- [ ] Code merged with passing CI.
- [ ] API contracts and docs updated.
- [ ] Telemetry added for new critical paths.
- [ ] Security review completed for auth/data exposure changes.
- [ ] Manual QA completed for happy path and primary failure paths.
