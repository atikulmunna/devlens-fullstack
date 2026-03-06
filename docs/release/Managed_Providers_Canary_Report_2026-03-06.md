# M3 Canary Cutover Report (Production Managed Providers)

Date: 2026-03-06  
Issue: #48  
Environment: production (`honest-youthfulness`)

## Summary

Production canary cutover to managed `DATABASE_URL`, `REDIS_URL`, and `QDRANT_URL` was executed and monitored.

Result: **NO-GO** for managed-provider production cutover at this time.  
Action taken: **Rollback completed** to Railway-internal Postgres/Redis/Qdrant endpoints.

## Canary Window Observations

- During managed-provider canary:
  - `/health/deps` returned:
    - `redis=true`
    - `postgres=true`
    - `qdrant=false`
    - `all_healthy=false`
  - One canary analyze submission reached terminal state (`done`), but dependency health showed Qdrant regression risk.

## Decision

Rollback criteria were met due to Qdrant dependency health failure in production (`qdrant=false`), so rollout was stopped and reverted.

## Rollback Execution

- Production backup snapshot source:
  - `C:\Users\Munna\AppData\Local\Temp\devlens_prod_canary_backup_20260306\backend.json`
  - `C:\Users\Munna\AppData\Local\Temp\devlens_prod_canary_backup_20260306\worker.json`
- Restored backend and worker variables:
  - `DATABASE_URL` -> `postgres.railway.internal`
  - `REDIS_URL` -> `redis.railway.internal`
  - `QDRANT_URL` -> `qdrant.railway.internal`
- Redeployed:
  - backend deployment: `SUCCESS` at `2026-03-06T15:46:56.432Z`
  - worker deployment: `SUCCESS` at `2026-03-06T15:46:59.761Z`

## Post-Rollback Validation

- `/health`: success, measured around `807.28 ms`
- `/health/deps`: success, measured around `1027.09 ms`
- `/health/deps` payload after rollback:
  - `redis=true`
  - `postgres=true`
  - `qdrant=true`
  - `all_healthy=true`

## Acceptance Criteria Mapping (#48)

- [x] Canary window completed and documented.
- [x] Final go/no-go decision recorded.
- [x] No critical regression left active in production core dependencies (rollback restored healthy state).

## Follow-Ups

1. Investigate managed Qdrant production connectivity/auth mismatch before next canary.
2. Add automated pre-cutover and post-cutover `/health/deps` gate to canary runbook.
3. Re-run canary with shorter blast radius and explicit timing SLO alarms.
