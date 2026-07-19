#!/usr/bin/env bash
# Run ON the EC2 host (Ubuntu 24.04), from the repo root, after .env.prod and at
# least one alpha user exist. Installs Docker, brings the stack up, runs migrations.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

# 1) Swap so the torch-containing backend image builds comfortably on 4GB.
if ! swapon --show | grep -q .; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "Added 2G swap"
fi

# 2) Docker (official convenience script)
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
  echo "Installed Docker"
fi

# 3) Preconditions
[ -f .env.prod ] || { echo "ERROR: .env.prod missing (copy deploy/env.prod.example and fill it)"; exit 1; }
grep -q '^DEVLENS_GATE_SECRET=' .env.prod || { echo "ERROR: set DEVLENS_GATE_SECRET in .env.prod (the private-alpha access key)"; exit 1; }

# 4) Build + start
sudo $COMPOSE up -d --build

# 5) Wait for backend health, then migrate
echo "Waiting for backend health..."
for _ in $(seq 1 80); do
  if sudo $COMPOSE exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=2)" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
sudo $COMPOSE exec -T backend alembic -c alembic.ini upgrade head

echo ""
echo "Bootstrap complete. Site: https://$(grep -E '^DEVLENS_DOMAIN=' .env.prod | cut -d= -f2)"
echo "Give testers their Basic Auth credentials, then GitHub login inside the app for chat."
