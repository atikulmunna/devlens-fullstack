$ErrorActionPreference = "Stop"

docker compose exec backend alembic -c alembic.ini upgrade head
