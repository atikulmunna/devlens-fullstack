#!/usr/bin/env bash
# Lets AWS Systems Manager (SSM) reach the DevLens box, so it needs no inbound SSH rule and a
# changing home IP no longer locks you out. Creates the devlens-ssm role and instance profile
# once (AWS-managed AmazonSSMManagedInstanceCore policy only), then attaches it to the instance.
# Safe to run again.
#
#   AWS_REGION=us-east-1 bash deploy/ssm-setup.sh <INSTANCE_ID>
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${1:?usage: bash deploy/ssm-setup.sh <INSTANCE_ID>}"
NAME="${SSM_ROLE_NAME:-devlens-ssm}"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! aws iam get-role --role-name "$NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$NAME" --assume-role-policy-document "$TRUST" \
    --description "DevLens box: Systems Manager access instead of inbound SSH" >/dev/null
  aws iam attach-role-policy --role-name "$NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  echo "Created role $NAME"
fi

if ! aws iam get-instance-profile --instance-profile-name "$NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$NAME" --role-name "$NAME"
  echo "Created instance profile $NAME"
fi

CURRENT=$(aws ec2 describe-iam-instance-profile-associations --region "$REGION" \
  --filters "Name=instance-id,Values=$INSTANCE_ID" \
  --query 'IamInstanceProfileAssociations[0].IamInstanceProfile.Arn' --output text)
if [ "$CURRENT" != "None" ]; then
  echo "$INSTANCE_ID already has an instance profile: $CURRENT"
else
  # A new instance profile takes a few seconds before EC2 accepts it.
  for attempt in 1 2 3 4 5 6; do
    if aws ec2 associate-iam-instance-profile --region "$REGION" --instance-id "$INSTANCE_ID" \
      --iam-instance-profile "Name=$NAME" >/dev/null 2>&1; then
      echo "Attached $NAME to $INSTANCE_ID"
      break
    fi
    if [ "$attempt" = 6 ]; then
      echo "Could not attach $NAME to $INSTANCE_ID; run this script again in a minute." >&2
      exit 1
    fi
    sleep 5
  done
fi

echo "The SSM agent on the box registers within a few minutes. Check with:"
echo "  aws ssm describe-instance-information --region $REGION --filters Key=InstanceIds,Values=$INSTANCE_ID"
