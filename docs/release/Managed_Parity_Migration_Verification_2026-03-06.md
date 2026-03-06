# M3 Managed Parity Migration Verification (Staging)

Issue: `#47`  
Date: `2026-03-06`  
Environment: `staging` (`honest-youthfulness` on Railway)

## 1. Scope

Verification executed for managed-provider parity migration:

- Schema migration verification on staging Supabase Postgres.
- Data consistency checks (row counts and key table spot checks).
- Vector collection integrity checks on Qdrant Cloud.
- Rollback dry-run and restoration validation in staging.

## 2. Schema Migration Verification

Command:

```powershell
docker compose run --rm -e DATABASE_URL=<staging_database_url> backend alembic current
```

Result:

- Alembic revision: `20260224_0007 (head)`.

Applied migration baseline was also executed on staging:

```powershell
docker compose run --rm -e DATABASE_URL=<staging_database_url> backend alembic upgrade head
```

Result:

- Upgraded through `20260224_0007` successfully.

## 3. Data Consistency Checks

### 3.1 Row counts (post-migration, post-validation run)

Snapshot query covered:

- `users`
- `repositories`
- `analysis_jobs`
- `code_chunks`
- `analysis_results`
- `chat_sessions`
- `chat_messages`
- `refresh_tokens`
- `share_tokens`
- `api_keys`
- `dead_letter_jobs`

Observed values:

- `users`: `0`
- `repositories`: `2`
- `analysis_jobs`: `2`
- `code_chunks`: `151`
- `analysis_results`: `1`
- `chat_sessions`: `0`
- `chat_messages`: `0`
- `refresh_tokens`: `0`
- `share_tokens`: `0`
- `api_keys`: `0`
- `dead_letter_jobs`: `1`

### 3.2 Key table spot checks

Submission check:

```powershell
POST /api/v1/repos/analyze
{"github_url":"https://github.com/pallets/itsdangerous"}
```

Observed:

- Job `aa85feb9-67cc-4d91-b2e7-f685bafd08ff` reached `done` at `progress=100`.
- Repo `pallets/itsdangerous` persisted with commit `672971d66a2ef9f85151e53283113f33d642dabd`.
- `analysis_results` row present for the validated repo.

Historical failure retained for auditability:

- Prior job `4736a208-3f26-4f64-877f-4a1db073afc4` failed with `EMBED_UPSERT_FAILED` (pre-fix Qdrant auth path).
- This failure entry remains visible in `analysis_jobs` and `dead_letter_jobs`.

## 4. Vector Collection Integrity (Qdrant Cloud)

Validation queries against staging Qdrant Cloud with API-key auth.

Observed:

- Collections count: `1`
- Target collection exists: `devlens_code_chunks` = `true`
- `points_count`: `22`
- `status`: `ok`

Interpretation:

- Collection exists and accepted vector upserts from staging worker.
- Non-zero points confirm end-to-end embed->upsert path is active.

## 5. Rollback Dry-Run (Validated)

Dry-run procedure:

1. Set staging backend `QDRANT_URL` to invalid host.
2. Wait for backend deploy.
3. Verify `/health/deps` fails on Qdrant (`qdrant=false`, `all_healthy=false`).
4. Restore original `QDRANT_URL`.
5. Redeploy backend and verify `/health/deps` recovers.

Observed:

- Failure state confirmed when invalid endpoint applied.
- Recovery to healthy state confirmed after restore (`redis=true`, `postgres=true`, `qdrant=true`, `all_healthy=true`).

## 6. Final Staging Health

Command:

```powershell
./scripts/verify_staging_connectivity.ps1 -BackendBaseUrl "https://backend-staging-cd1e.up.railway.app"
```

Result:

- Passed (`[ok] staging managed-provider connectivity verified`).

## 7. Conclusion

`#47` acceptance is satisfied in staging:

- Migration checklist executed with evidence.
- Verification report recorded in `docs/release/`.
- Rollback path dry-run validated.

