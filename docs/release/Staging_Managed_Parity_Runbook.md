# M3 Staging Managed Parity Runbook

Issue: `#46`  
Goal: provision staging parity with Supabase Postgres, Upstash Redis, and Qdrant Cloud, then verify backend/worker connectivity.

## 1. Prerequisites

- Railway CLI authenticated (`railway whoami`)
- Railway project linked
- Managed providers provisioned:
  - Supabase project + connection string
  - Upstash Redis database + `rediss://` URL
  - Qdrant Cloud cluster + HTTPS endpoint and API key (if required by plan)
- Local files created from templates:
  - `backend/.env.staging` (copy from `backend/.env.staging.example`)
  - `workers/.env.staging` (copy from `workers/.env.staging.example`)

## 2. Configure Staging Env Files

Fill these minimum keys with real staging values:

- Backend:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `QDRANT_URL`
  - `GITHUB_*`
  - `FRONTEND_URL`
  - `JWT_SECRET`
- Worker:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `QDRANT_URL`
  - `OPENROUTER_API_KEY`
  - `GROQ_API_KEY`

## 3. Deploy Backend + Worker to Railway Staging

```powershell
./scripts/deploy_railway_staging.ps1 `
  -RailwayToken "<RAILWAY_TOKEN>" `
  -ProjectName "devlens-fullstack" `
  -BackendService "backend" `
  -WorkerService "worker" `
  -BackendEnvFile "backend/.env.staging" `
  -WorkerEnvFile "workers/.env.staging"
```

## 4. Verify Connectivity and Health

Run:

```powershell
./scripts/verify_staging_connectivity.ps1 `
  -BackendBaseUrl "https://<staging-backend-domain>"
```

Optional worker metrics check:

```powershell
./scripts/verify_staging_connectivity.ps1 `
  -BackendBaseUrl "https://<staging-backend-domain>" `
  -WorkerMetricsUrl "https://<staging-worker-metrics-url>"
```

Pass criteria:
- `/health` returns `status=ok`
- `/health/deps` returns `all_healthy=true`
- `postgres=true`, `redis=true`, `qdrant=true`

## 5. Evidence to Attach to Issue/PR

- Deploy command output (backend + worker)
- `verify_staging_connectivity.ps1` output
- Railway variables screenshot/export for staging environment
- Staging backend domain used in verification

## 6. Exit Conditions

- Backend and worker are deployed in staging using managed provider URLs.
- Dependency health checks pass from staging backend.
- Runbook and templates are committed and reproducible.
