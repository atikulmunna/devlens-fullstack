# M3 Staging Managed Providers Provisioning Verification

Date: 2026-03-07  
Issue: #46  
Environment: `staging` (Railway project `honest-youthfulness`)

## Summary

Staging managed-provider parity is provisioned and validated for:

- Supabase Postgres
- Upstash Redis
- Qdrant Cloud

Backend and worker are deployed in staging and dependency health checks pass.

## Deployed Services

- Backend: `https://backend-staging-cd1e.up.railway.app`
- Worker: deployed to staging service `worker`

## Managed Endpoint Verification

Verified Railway staging variables resolve to managed provider hosts:

- Backend
  - `DATABASE_URL` -> `aws-1-ap-northeast-1.pooler.supabase.com`
  - `REDIS_URL` -> `fit-shiner-41050.upstash.io`
  - `QDRANT_URL` -> `e0603748-d521-4a35-bdf1-618c3d58246f.eu-west-2-0.aws.cloud.qdrant.io`
- Worker
  - `DATABASE_URL` -> `aws-1-ap-northeast-1.pooler.supabase.com`
  - `REDIS_URL` -> `fit-shiner-41050.upstash.io`
  - `QDRANT_URL` -> `e0603748-d521-4a35-bdf1-618c3d58246f.eu-west-2-0.aws.cloud.qdrant.io`

## Connectivity and Health Checks

Executed:

```powershell
./scripts/verify_staging_connectivity.ps1 -BackendBaseUrl "https://backend-staging-cd1e.up.railway.app"
```

Output included:

- `[check] backend-health`
- `[check] backend-health-deps`
- `[ok] staging managed-provider connectivity verified`

`GET /health/deps` returned:

- `redis=true`
- `postgres=true`
- `qdrant=true`
- `all_healthy=true`

## Implementation Note

Deploy scripts now support authenticated Railway CLI sessions without requiring `RAILWAY_TOKEN` to be passed explicitly:

- `scripts/deploy_railway_prod.ps1`
- `scripts/deploy_railway_staging.ps1`

## Acceptance Criteria Mapping (#46)

- [x] Staging services reachable and authenticated.
- [x] Backend and worker boot successfully in staging.
- [x] Health checks pass for DB/Redis/Qdrant dependencies.
