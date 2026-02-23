#!/usr/bin/env bash
set -euo pipefail

docker compose exec -e PYTHONPATH=/app worker sh -lc "cd /app && pytest -q"
