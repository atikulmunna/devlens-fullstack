# CI/CD Runbook (DEV-073)

This runbook defines required checks, deployment behavior, notifications, and rollback steps.

## Workflow

- GitHub Actions workflow: `.github/workflows/ci-cd.yml`
- Trigger:
- Pull requests to `main`
- Pushes to `main`

Jobs:
- `Lint And Static Checks`
- `Backend Tests`
- `Worker Tests`
- `Build Service Images`
- `Deploy Main` (push to `main` only)
- `Deployment Notification` (push to `main` only)

## Required Branch Checks

Enable branch protection for `main` and require these checks:

1. `Lint And Static Checks`
2. `Backend Tests`
3. `Worker Tests`
4. `Build Service Images`
5. `Backend Coverage` (from `.github/workflows/backend-coverage.yml`)

Recommended:
- Require pull request before merge.
- Require linear history.
- Dismiss stale approvals on new commits.

## Deployment Output

On successful `main` deploy:
- Service images are built and pushed to GHCR with `${GITHUB_SHA}` tags.
- A `deployment-manifest` artifact is uploaded with image tags and previous SHA.
- Workflow summary includes rollback instructions.

## Notifications

- Deployment status is always summarized in workflow summary.
- Optional webhook notification:
- Set repository secret `DEPLOY_WEBHOOK_URL`
- If set, workflow posts a JSON payload with deployment status text.

## Rollback

If deployment fails or post-deploy checks regress:

1. Identify previous successful SHA from workflow (`github.event.before`) or last good run.
2. Redeploy previously published image tags for:
- `devlens-backend:<previous_sha>`
- `devlens-worker:<previous_sha>`
- `devlens-frontend:<previous_sha>`
3. If schema changes were released, run safe down-migration or restore DB snapshot.
4. Validate:
- `/health`
- `/health/deps`
- critical flows: auth refresh, analyze submission, dashboard load, chat stream
5. Post incident note with root cause and corrective action.
