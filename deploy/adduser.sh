#!/usr/bin/env bash
# Add or update an alpha tester's Basic Auth credential, then reload Caddy.
# Run ON the host, from the repo root.
#
#   bash deploy/adduser.sh alice            # generates a random password
#   bash deploy/adduser.sh alice s3cret-pw  # sets a specific password
#
# Revoke someone by deleting their line from deploy/alpha_users and reloading Caddy.
set -euo pipefail

USER_NAME="${1:?usage: adduser.sh <username> [password]}"
PASSWORD="${2:-$(openssl rand -base64 12)}"

# Hash with Caddy's bcrypt (uses the same image the stack runs).
HASH=$(sudo docker run --rm caddy:2-alpine caddy hash-password --plaintext "$PASSWORD")

touch deploy/alpha_users
# Replace any existing entry for this user, then append the new one. Update the file IN
# PLACE (truncate + rewrite the same inode) rather than mv/rename: Docker bind-mounts this
# single file by inode, so a rename would leave the Caddy container reading the old file.
grep -v "^${USER_NAME} " deploy/alpha_users > deploy/.alpha_users.tmp 2>/dev/null || true
cat deploy/.alpha_users.tmp > deploy/alpha_users
rm -f deploy/.alpha_users.tmp
echo "${USER_NAME} ${HASH}" >> deploy/alpha_users

echo "User:     ${USER_NAME}"
echo "Password: ${PASSWORD}"

# Reload Caddy in place if the stack is running.
if sudo docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T caddy \
     caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
  echo "Caddy reloaded, credential is live."
else
  echo "(Caddy not running yet, credential will apply when the stack starts.)"
fi
