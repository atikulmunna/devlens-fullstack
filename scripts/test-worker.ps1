$ErrorActionPreference = "Stop"

docker compose run --rm -e PYTHONPATH=/app worker sh -lc "cd /app && pytest -q"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
