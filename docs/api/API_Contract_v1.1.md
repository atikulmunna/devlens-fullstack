# DevLens API Contract v1.1

SRD reference: `DevLens_SRD.md` (v1.1, February 23, 2026)

Base path: `/api/v1`

Observability headers:
- All backend responses include `X-Trace-Id` for request correlation.

## Error Envelope (all non-2xx responses)

```json
{
  "error": {
    "code": "STRING_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

Common `error.code` values:
- `BAD_REQUEST`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `NOT_FOUND`
- `CONFLICT`
- `VALIDATION_ERROR`
- `RATE_LIMITED`
- `UPSTREAM_ERROR`
- `INTERNAL_ERROR`

## Auth Endpoints

### `GET /auth/github`
- Purpose: Start GitHub OAuth flow.
- Query params:
  - `next` (optional): frontend-relative return path, default `/profile`.
- Success:
  - `302 Found`: redirects to GitHub authorize URL.

### `GET /auth/callback`
- Purpose: Process OAuth callback and create session cookies.
- Query params:
  - `code` (required): GitHub OAuth code.
  - `state` (required): signed state payload.
- Success:
  - `302 Found`: redirects to frontend `next` path.
  - Sets cookies:
    - `devlens_refresh_token` (HttpOnly, SameSite=Lax, Secure in non-local env)
    - `devlens_csrf_token` (SameSite=Lax, Secure in non-local env)
- Errors:
  - `400`: invalid state or callback data.
  - `502`: invalid upstream profile payload.

### `POST /auth/refresh`
- Purpose: Rotate refresh token and issue new access token.
- Security requirements:
  - Cookie: `devlens_refresh_token`
  - Cookie + header match: `devlens_csrf_token` and `x-csrf-token`
  - Valid `Origin` or `Referer` matching configured frontend origin
- Success `200`:
```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "expires_in_seconds": 900
}
```
- Errors:
  - `401`: missing/invalid/revoked/expired token.
  - `403`: origin or CSRF validation failure.

### `DELETE /auth/logout`
- Purpose: Revoke current refresh token and clear cookies.
- Security requirements:
  - Same origin + CSRF checks as `/auth/refresh`.
- Success:
  - `204 No Content`
- Errors:
  - `403`: origin or CSRF validation failure.

### `GET /auth/me`
- Purpose: Return current authenticated user profile.
- Auth: `Authorization: Bearer <access_token>`
- Success `200`:
```json
{
  "id": "uuid",
  "github_id": 123,
  "username": "octocat",
  "email": "octo@example.com",
  "avatar_url": "https://..."
}
```
- Errors:
  - `401`: missing/invalid token.

## Repository Analysis Endpoints

### `POST /repos/analyze`
- Purpose: Create analysis job or return deduped existing job.
- Headers:
  - `Idempotency-Key` (optional): duplicate suppression key.
- Body:
```json
{
  "github_url": "https://github.com/owner/repo",
  "force_reanalyze": false
}
```
- Success `200`:
```json
{
  "job_id": "uuid",
  "repo_id": "uuid",
  "status": "queued",
  "cache_hit": false,
  "commit_sha": "abcdef123"
}
```
- Errors:
  - `400`: invalid URL/unsupported repo.
  - `429`: rate limit exceeded.
  - `502`: GitHub upstream failure.
- Rate limit headers:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset` (epoch seconds)
  - `Retry-After` (on `429`)

## Share Token Endpoints

### `POST /export/{repo_id}/share`
- Purpose: Create a signed public share link for a repository analysis.
- Auth: `Authorization: Bearer <access_token>`
- Body:
```json
{
  "ttl_days": 7
}
```
- `ttl_days` is optional, defaults to `SHARE_TOKEN_TTL_DAYS`, max `30`.
- Success `200`:
```json
{
  "share_id": "uuid",
  "share_token": "jwt",
  "share_url": "https://app.example/share/<jwt>",
  "expires_at": "2026-03-01T12:00:00Z"
}
```
- Errors:
  - `401`: unauthorized.
  - `404`: repository or analysis result not found.

### `DELETE /export/share/{share_id}`
- Purpose: Revoke an existing share token.
- Auth: `Authorization: Bearer <access_token>`
- Success:
  - `204 No Content`
- Errors:
  - `401`: unauthorized.
  - `404`: share token not found for current user.

### `GET /share/{token}`
- Purpose: Resolve public shared analysis payload.
- Auth: none (public endpoint).
- Success `200`:
```json
{
  "repo_id": "uuid",
  "repository": {
    "github_url": "https://github.com/owner/repo",
    "full_name": "owner/repo",
    "owner": "owner",
    "name": "repo"
  },
  "analysis": {
    "quality_score": 74,
    "architecture_summary": "..."
  },
  "shared_at": "2026-02-23T12:00:00Z",
  "expires_at": "2026-03-01T12:00:00Z"
}
```
- Errors:
  - `401`: invalid/expired/revoked token.
  - `404`: repository or analysis payload missing.

## Chat Endpoints

### `POST /chat/sessions`
- Purpose: Create a chat session for a repository.
- Auth: `Authorization: Bearer <access_token>`
- Body:
```json
{
  "repo_id": "uuid"
}
```
- Success `200`:
```json
{
  "session_id": "uuid",
  "repo_id": "uuid",
  "created_at": "2026-02-23T13:00:00Z"
}
```

### `GET /chat/sessions`
- Purpose: List current user chat sessions (optionally scoped by repository).
- Auth: `Authorization: Bearer <access_token>`
- Query params:
  - `repo_id` (optional): UUID, filters sessions for one repository.
- Success `200`:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "repo_id": "uuid",
      "created_at": "2026-02-23T13:00:00Z",
      "message_count": 2,
      "last_message_preview": "Relevant code was found in..."
    }
  ]
}
```

### `GET /chat/sessions/{session_id}`
- Purpose: Load session and full message history.
- Auth: `Authorization: Bearer <access_token>`
- Success `200`:
```json
{
  "id": "uuid",
  "repo_id": "uuid",
  "user_id": "uuid",
  "created_at": "2026-02-23T13:00:00Z",
  "messages": [
    {
      "id": "uuid",
      "role": "assistant",
      "content": "Relevant code was found...",
      "source_citations": {
        "citations": [],
        "no_citation": true
      },
      "created_at": "2026-02-23T13:00:10Z"
    }
  ]
}
```

### `DELETE /chat/sessions/{session_id}`
- Purpose: Delete session and all messages.
- Auth: `Authorization: Bearer <access_token>`
- Success:
  - `204 No Content`

### `GET /chat/repos/{repo_id}/suggestions`
- Purpose: Return suggested question chips for chat bootstrap.
- Auth: `Authorization: Bearer <access_token>`
- Query params:
  - `limit` (optional, default `5`, min `1`, max `10`)
- Success `200`:
```json
{
  "repo_id": "uuid",
  "suggestions": [
    "What are the main architecture components in this repository?",
    "Where is authentication and token handling implemented?"
  ]
}
```

### `POST /chat/sessions/{session_id}/message` (SSE)
- Purpose: Persist user message, run retrieval, persist assistant response, and stream assistant output.
- Auth: `Authorization: Bearer <access_token>`
- Body:
```json
{
  "content": "Where is auth refresh handled?",
  "top_k": 5
}
```
- Stream contract:
```text
event: delta
data: {"token":"Relevant "}

event: done
data: {"message_id":"uuid","citations":[...],"no_citation":false}
```
- Citation guarantee:
  - Assistant response always stores `source_citations` with either:
    - `citations: [ ... ]` and `no_citation: false`, or
    - `citations: []` and `no_citation: true`

### `GET /repos/{repo_id}/status` (SSE)
- Purpose: Stream job status updates as Server-Sent Events.
- Query params:
  - `once` (optional, default `false`):
    - `false`: stream until terminal event.
    - `true`: emit latest event once and close.

#### Event types and payloads

`event: progress`
```json
{
  "job_id": "uuid",
  "stage": "queued|cloning|parsing|embedding|analyzing",
  "progress": 0,
  "message": "stage in progress",
  "eta_seconds": null
}
```

`event: done`
```json
{
  "job_id": "uuid",
  "stage": "done",
  "progress": 100
}
```

`event: error`
```json
{
  "job_id": "uuid",
  "stage": "failed",
  "progress": 100,
  "code": "MACHINE_READABLE_ERROR",
  "message": "failure reason"
}
```

#### Reconnection behavior
- Client reconnect is supported by re-subscribing to the same endpoint.
- When `once=true`, server emits one latest state event and closes.
- Without `once`, server emits changes only and stops on terminal `done`/`error`.

### `GET /repos/{repo_id}/search/lexical`
- Purpose: Execute keyword retrieval using PostgreSQL FTS (`plainto_tsquery` + `ts_rank_cd`).
- Query params:
  - `q` (required): search keywords.
  - `limit` (optional, default `20`, max `100`).
- Success `200`:
```json
{
  "repo_id": "uuid",
  "query": "payment service",
  "total": 2,
  "results": [
    {
      "chunk_id": "uuid",
      "file_path": "src/payment/service.py",
      "start_line": 1,
      "end_line": 40,
      "language": "py",
      "score": 0.34
    }
  ]
}
```
- Errors:
  - `400`: empty/invalid query.
  - `404`: repository not found.

### `GET /repos/{repo_id}/search/hybrid`
- Purpose: Hybrid retrieval = Qdrant dense + PostgreSQL FTS lexical + deterministic rerank.
- Query params:
  - `q` (required): question/keywords.
  - `limit` (optional, default `20`, max `100`).
- Success `200`:
```json
{
  "repo_id": "uuid",
  "query": "jwt refresh token",
  "total": 2,
  "results": [
    {
      "chunk_id": "uuid",
      "file_path": "src/auth/jwt.py",
      "start_line": 1,
      "end_line": 40,
      "language": "py",
      "dense_score": 0.84,
      "lexical_score": 0.42,
      "rerank_score": 0.73
    }
  ]
}
```
- Errors:
  - `400`: empty/invalid query.
  - `404`: repository not found.
  - `502`: vector search upstream failure.
- Security/Isolation:
  - Dense retrieval always sends mandatory Qdrant payload filter for `repo_id`; unscoped retrieval is rejected server-side.

### `GET /repos/{repo_id}/dashboard`
- Purpose: Return repository metadata and latest analysis payload for dashboard rendering.
- Success `200`:
```json
{
  "repo_id": "uuid",
  "repository": {
    "id": "uuid",
    "github_url": "https://github.com/owner/repo",
    "full_name": "owner/repo",
    "owner": "owner",
    "name": "repo",
    "default_branch": "main",
    "latest_commit_sha": "abcdef123",
    "description": "Repository description",
    "stars": 120,
    "forks": 31,
    "language": "Python",
    "size_kb": 1024
  },
  "analysis": {
    "quality_score": 74,
    "architecture_summary": "service-oriented modules ...",
    "language_breakdown": {"Python": 80, "TypeScript": 20},
    "contributor_stats": {"total": 7},
    "tech_debt_flags": {"todo": 14, "fixme": 3},
    "file_tree": {"type": "dir", "name": "/", "children": []},
    "created_at": "2026-02-23T12:00:00Z"
  },
  "has_analysis": true
}
```
- Empty analysis case:
  - `has_analysis` is `false`, `analysis` is `null`.
- Errors:
  - `404`: repository not found.

## OpenAPI Source of Truth

- Live schema: `GET /openapi.json`
- Swagger UI: `GET /docs`
- Version alignment: this contract and OpenAPI metadata target SRD v1.1 (February 23, 2026).
- OpenAPI examples are defined for:
  - Auth: `/auth/refresh`, `/auth/me`
  - Analyze: `/repos/analyze`
  - Share/export: `/export/{repo_id}/share`, `/share/{token}`
  - Chat: `/chat/sessions`, `/chat/sessions/{session_id}/message` (SSE sample)

## Metrics Endpoint

- `GET /metrics` (Prometheus exposition format)
- Baseline metrics emitted:
  - `devlens_http_request_duration_seconds`
  - `devlens_sse_startup_latency_seconds`
  - `devlens_analysis_stage_duration_seconds` (worker process)
