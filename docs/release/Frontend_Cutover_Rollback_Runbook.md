# Frontend Migration Cutover and Rollback Runbook

Issue: `#51`  
Scope: progressive cutover from legacy `frontend/` to `frontend-next/` with explicit rollback path.

## 1. Strategy

- Keep both frontends deployable in parallel:
  - Legacy (`frontend/`) as current stable baseline
  - Next scaffold (`frontend-next/`) as candidate
- Route-level migration:
  - Phase A: `/`
  - Phase B: `/analyze`
  - Phase C: `/dashboard/[repoId]`
- Move one phase at a time and monitor before proceeding.

## 2. Required Observability

From `frontend-next`:
- Route load latency events (`route_load`) from `components/frontend-telemetry.tsx`
- Client runtime errors (`client_error`, `unhandled_rejection`)
- Server log ingestion endpoint:
  - `POST /api/internal/frontend-telemetry`

Monitor during each phase:
- 4xx/5xx rate
- analyze->dashboard completion rate
- client error event count
- page load latency trend

## 3. Pre-Cutover Validation

Run parity checks against both deployments:

```powershell
./scripts/validate_frontend_cutover.ps1 `
  -LegacyBaseUrl "https://<legacy-frontend-domain>" `
  -NextBaseUrl "https://<next-frontend-domain>" `
  -SampleRepoId "<known_repo_id>"
```

Expected result: all checks `[ok]`.

## 4. Progressive Cutover Plan

1. Deploy `frontend-next` to preview/staging.
2. Validate with `validate_frontend_cutover.ps1`.
3. Shift low-risk traffic cohort to next frontend:
   - internal users first
   - then small external slice
4. Monitor for one full observation window.
5. Continue to next route phase only if error/latency remain within thresholds.

## 5. Rollback Procedure

Trigger rollback immediately if:
- critical auth/session regression
- analyze->dashboard flow breaks
- sustained increase in 5xx/client errors

Rollback steps:
1. Repoint traffic/router/domain to legacy frontend deployment.
2. Verify legacy health:
   - `/health`
   - `/`
   - `/analyze`
   - `/dashboard/<sample_repo_id>`
3. Announce rollback in release channel with timestamp + reason.
4. Capture incident notes and affected commit SHA.

## 6. Post-Cutover Exit Criteria

- No critical incident during phased rollout.
- All three critical routes stable on `frontend-next`.
- Rollback drill command and validation script tested.
