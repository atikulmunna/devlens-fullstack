#!/usr/bin/env bash
set -euo pipefail

docker compose run --rm -e PYTHONPATH=/app worker sh -lc "cd /app && pytest -q"
