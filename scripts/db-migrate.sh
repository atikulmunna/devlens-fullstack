#!/usr/bin/env bash
set -euo pipefail

docker compose exec backend alembic -c alembic.ini upgrade head
