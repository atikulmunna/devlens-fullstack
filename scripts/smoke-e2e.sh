#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
REPO_URL="${SMOKE_REPO_URL:-https://github.com/octocat/Hello-World}"
MAX_POLLS="${SMOKE_MAX_POLLS:-300}"
POLL_DELAY_SECONDS="${SMOKE_POLL_DELAY_SECONDS:-2}"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for smoke-e2e.sh"
  exit 1
fi

echo "[smoke] backend: ${BACKEND_URL}"
echo "[smoke] repo: ${REPO_URL}"

echo "[smoke] waiting for backend health..."
for _ in $(seq 1 60); do
  if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "${BACKEND_URL}/health" >/dev/null
curl -fsS "${BACKEND_URL}/health/deps" >/dev/null

echo "[smoke] submitting analyze job..."
analyze_payload="$(jq -n --arg url "${REPO_URL}" '{github_url: $url}')"
analyze_resp="$(curl -fsS -X POST "${BACKEND_URL}/api/v1/repos/analyze" -H "Content-Type: application/json" -d "${analyze_payload}")"
repo_id="$(echo "${analyze_resp}" | jq -r '.repo_id')"
job_id="$(echo "${analyze_resp}" | jq -r '.job_id')"
if [[ -z "${repo_id}" || "${repo_id}" == "null" || -z "${job_id}" || "${job_id}" == "null" ]]; then
  echo "[smoke] analyze response missing repo_id/job_id: ${analyze_resp}"
  exit 1
fi
echo "[smoke] job_id=${job_id} repo_id=${repo_id}"

echo "[smoke] waiting for terminal status..."
terminal_event=""
terminal_payload=""
for _ in $(seq 1 "${MAX_POLLS}"); do
  sse="$(curl -fsS "${BACKEND_URL}/api/v1/repos/${repo_id}/status?once=true")"
  event_name="$(echo "${sse}" | sed -n 's/^event: //p' | tr -d '\r' | head -n1)"
  event_payload="$(echo "${sse}" | sed -n 's/^data: //p' | tr -d '\r' | head -n1)"
  if [[ "${event_name}" == "done" || "${event_name}" == "error" ]]; then
    terminal_event="${event_name}"
    terminal_payload="${event_payload}"
    break
  fi
  dashboard_probe="$(curl -fsS "${BACKEND_URL}/api/v1/repos/${repo_id}/dashboard" || true)"
  has_analysis_probe="$(echo "${dashboard_probe}" | jq -r '.has_analysis // false' 2>/dev/null || echo "false")"
  if [[ "${has_analysis_probe}" == "true" ]]; then
    terminal_event="done"
    terminal_payload='{"source":"dashboard_probe"}'
    break
  fi
  sleep "${POLL_DELAY_SECONDS}"
done

if [[ -z "${terminal_event}" ]]; then
  echo "[smoke] status polling timed out"
  echo "[smoke] backend logs (tail 120):"
  docker compose logs backend --tail 120 || true
  echo "[smoke] worker logs (tail 120):"
  docker compose logs worker --tail 120 || true
  exit 1
fi

echo "[smoke] terminal event: ${terminal_event}"
if [[ "${terminal_event}" == "error" ]]; then
  echo "[smoke] terminal payload: ${terminal_payload}"
  exit 1
fi

dashboard_resp="$(curl -fsS "${BACKEND_URL}/api/v1/repos/${repo_id}/dashboard")"
has_analysis="$(echo "${dashboard_resp}" | jq -r '.has_analysis')"
if [[ "${has_analysis}" != "true" ]]; then
  echo "[smoke] dashboard has_analysis=false: ${dashboard_resp}"
  exit 1
fi
echo "[smoke] dashboard verified"

echo "[smoke] minting temporary auth token..."
backend_cid="$(docker compose ps -q backend 2>/dev/null | tr -d '\r\n')"
if [[ -z "${backend_cid}" ]]; then
  backend_cid="$(docker ps --filter "label=com.docker.compose.service=backend" --format '{{.ID}}' | head -n1 | tr -d '\r\n')"
fi
if [[ -z "${backend_cid}" ]]; then
  echo "[smoke] backend container not found"
  exit 1
fi

token="$(docker exec -i "${backend_cid}" python - <<'PY'
from sqlalchemy import select
from uuid import uuid4
from app.db.session import SessionLocal
from app.db.models import User
from app.services.tokens import create_access_token

TEST_GITHUB_ID = 999999001
TEST_USERNAME = "smoke-bot"

db = SessionLocal()
try:
    user = db.execute(select(User).where(User.github_id == TEST_GITHUB_ID)).scalar_one_or_none()
    if user is None:
        user = User(id=uuid4(), github_id=TEST_GITHUB_ID, username=TEST_USERNAME, email=None, avatar_url=None)
        db.add(user)
        db.commit()
        db.refresh(user)
    print(create_access_token(user.id))
finally:
    db.close()
PY
)"

if [[ -z "${token}" ]]; then
  echo "[smoke] failed to mint access token"
  exit 1
fi

echo "[smoke] creating chat session..."
chat_create_resp="$(curl -fsS -X POST "${BACKEND_URL}/api/v1/chat/sessions" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg repo "${repo_id}" '{repo_id: $repo}')")"
session_id="$(echo "${chat_create_resp}" | jq -r '.session_id')"
if [[ -z "${session_id}" || "${session_id}" == "null" ]]; then
  echo "[smoke] session create failed: ${chat_create_resp}"
  exit 1
fi

echo "[smoke] streaming chat message..."
chat_sse="$(curl -fsS -X POST "${BACKEND_URL}/api/v1/chat/sessions/${session_id}/message" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  -d '{"content":"What are the main architecture components?","top_k":5}')"
if ! echo "${chat_sse}" | grep -q "event: done"; then
  echo "[smoke] chat stream missing done event: ${chat_sse}"
  exit 1
fi

echo "[smoke] E2E smoke passed"
