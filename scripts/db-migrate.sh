#!/usr/bin/env bash
set -euo pipefail

backend_cid="$(docker compose ps -q backend 2>/dev/null | tr -d '\r\n')"
if [[ -z "${backend_cid}" ]]; then
  backend_cid="$(docker ps --filter "label=com.docker.compose.service=backend" --format '{{.ID}}' | head -n1 | tr -d '\r\n')"
fi
if [[ -z "${backend_cid}" ]]; then
  echo "backend container not found"
  exit 1
fi

docker exec -i "${backend_cid}" alembic -c alembic.ini upgrade head
