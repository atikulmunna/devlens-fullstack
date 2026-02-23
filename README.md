# DevLens Fullstack

AI-powered GitHub repository analyzer with RAG chat and code insights dashboard.

## Documentation

- Product SRD: `DevLens_SRD.md`
- Execution checklist: `docs/planning/Implementation_Checklist.md`
- Golden relevance eval (DEV-071): `docs/evaluation/DEV-071_Golden_Relevance.md`
- Load/SLA validation (DEV-072): `docs/testing/DEV-072_Load_SLA_Validation.md`

## Current Status

Planning and architecture are finalized in SRD v1.1. Implementation is tracked via `DEV-*` tickets.

## Project Structure

- `backend/` FastAPI API service scaffold
- `workers/` background worker scaffold
- `frontend/` frontend scaffold
- `docs/planning/` implementation planning documents
- `scripts/` local developer startup/shutdown scripts

## Local Development

1. Start stack: `./scripts/dev-up.ps1`
2. Stop stack: `./scripts/dev-down.ps1`
3. Check services: `docker compose ps`
4. Apply DB migrations: `./scripts/db-migrate.ps1`
5. Run backend tests: `./scripts/test-backend.ps1`
6. Run worker tests: `./scripts/test-worker.ps1`

Service env templates:

- `backend/.env.example`
- `workers/.env.example`
- `frontend/.env.example`

Config validation is fail-fast at startup for required environment variables.

Auth security controls:

- Refresh/logout endpoints require trusted `Origin`/`Referer` (frontend URL).
- Refresh/logout endpoints require CSRF double-submit (`devlens_csrf_token` cookie + `X-CSRF-Token` header).

Default endpoints:

- Backend health: `http://localhost:8000/health`
- Frontend health: `http://localhost:3000/health`
- Qdrant health: `http://localhost:6333/healthz`
