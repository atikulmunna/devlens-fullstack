# Phase 5 Deployment Checklist

## Current Progress

- Frontend deployed on Vercel:
  - `https://frontend-y10kqztcm-atikulmunnas-projects.vercel.app`
- Railway CLI installed but not authenticated in this non-interactive shell.

## Required Inputs

1. `RAILWAY_TOKEN` (personal/team token from Railway account settings)
2. Production backend env file at `backend/.env` with real secrets/URLs
3. Production worker env file at `workers/.env` with real secrets/URLs

## Deploy Backend + Worker to Railway

```powershell
./scripts/deploy_railway_prod.ps1 `
  -RailwayToken "<RAILWAY_TOKEN>" `
  -ProjectName "devlens-fullstack" `
  -EnvironmentName "production" `
  -BackendEnvFile "backend/.env" `
  -WorkerEnvFile "workers/.env"
```

Outputs:
- Railway backend deployment
- Railway worker deployment
- Generated backend public domain

## Wire Frontend to Backend URL (Vercel)

After Railway backend domain is known:

```powershell
vercel env add NEXT_PUBLIC_API_URL production
vercel --cwd frontend --prod --yes
```

Set value to:
- `https://<railway-backend-domain>`

## Post-Deploy Validation

1. Backend
- `GET https://<backend-domain>/health`
- `GET https://<backend-domain>/health/deps`
- `GET https://<backend-domain>/metrics`

2. Frontend
- open Vercel production URL
- verify `/analyze`, `/dashboard/{repo}`, `/dashboard/{repo}/chat`

3. Full release smoke
- execute `docs/testing/Release_QA_v1.1.md` against production URLs
