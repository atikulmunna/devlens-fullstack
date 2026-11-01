#!/usr/bin/env bash
# Runs a shell command on the DevLens box through Systems Manager (no SSH) as the ubuntu user,
# waits for it, and prints its output. Needs deploy/ssm-setup.sh to have run once.
#
#   bash deploy/remote.sh <INSTANCE_ID> 'cd ~/devlens-fullstack && git log -1 --oneline'
#
# Output is capped by SSM at about 24 KB; for long builds, write a log on the box and tail it.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${1:?usage: bash deploy/remote.sh <INSTANCE_ID> '<command>'}"
COMMAND="${2:?usage: bash deploy/remote.sh <INSTANCE_ID> '<command>'}"

# Base64 keeps quotes and $ in the command intact through the JSON parameter. The command runs from
# a file with stdin closed: fed through stdin, anything reading it (docker compose exec -T) would
# swallow the rest of the command.
ENCODED=$(printf '%s' "$COMMAND" | base64 | tr -d '\n')
RUN="f=\$(mktemp) && echo $ENCODED | base64 -d > \$f && chmod 644 \$f && sudo -iu ubuntu bash \$f < /dev/null; s=\$?; rm -f \$f; exit \$s"
COMMAND_ID=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --comment "devlens remote.sh" \
  --parameters "commands=[\"$RUN\"],executionTimeout=[\"3600\"]" \
  --query 'Command.CommandId' --output text)

while true; do
  STATUS=$(aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in
    Pending | InProgress | Delayed) sleep 3 ;;
    *) break ;;
  esac
done

aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" --query StandardOutputContent --output text
ERRORS=$(aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" --query StandardErrorContent --output text)
if [ -n "$ERRORS" ] && [ "$ERRORS" != "None" ]; then
  printf '%s\n' "$ERRORS" >&2
fi
[ "$STATUS" = "Success" ]
