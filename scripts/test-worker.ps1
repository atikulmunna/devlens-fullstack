$ErrorActionPreference = "Stop"

docker compose exec -e PYTHONPATH=/app worker sh -lc "cd /app && pytest -q"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
