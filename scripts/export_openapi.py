"""Print the backend's OpenAPI schema; the frontend's API types are generated from it.

From the repo root, with the stack up:
  docker compose exec -T -e PYTHONPATH=/app backend python - < scripts/export_openapi.py > frontend-next/lib/openapi.json
  npm --prefix frontend-next run gen:api
"""

import json
import sys

from app.main import app

spec = app.openapi()
# The served title comes from APP_NAME, which differs per environment; keep the committed copy stable.
spec["info"]["title"] = "DevLens API"
json.dump(spec, sys.stdout, indent=2)
sys.stdout.write("\n")
