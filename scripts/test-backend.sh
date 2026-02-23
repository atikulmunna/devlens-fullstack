#!/usr/bin/env bash
set -euo pipefail

docker compose exec -e PYTHONPATH=/app backend pytest -q
