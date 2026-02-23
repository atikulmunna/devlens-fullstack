$ErrorActionPreference = "Stop"

docker compose exec -e PYTHONPATH=/app backend pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
