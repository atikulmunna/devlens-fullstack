#!/usr/bin/env bash
# Provision a single EC2 host for the DevLens private alpha.
# Requires: aws cli (configured), curl. Idempotent-ish: reuses existing key/SG.
#
#   AWS_REGION=us-east-1 INSTANCE_TYPE=t3.medium bash deploy/provision-aws.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
KEY_NAME="${KEY_NAME:-devlens-key}"
SG_NAME="${SG_NAME:-devlens-alpha-sg}"
DISK_GB="${DISK_GB:-30}"
NAME_TAG="${NAME_TAG:-devlens-alpha}"

echo "Region=$REGION Type=$INSTANCE_TYPE Key=$KEY_NAME SG=$SG_NAME Disk=${DISK_GB}GB"

# 1) Key pair (private key saved locally as <KEY_NAME>.pem)
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" >/dev/null 2>&1; then
  aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$REGION" \
    --query 'KeyMaterial' --output text > "${KEY_NAME}.pem"
  chmod 600 "${KEY_NAME}.pem"
  echo "Created key pair -> ${KEY_NAME}.pem (keep this safe)"
else
  echo "Key pair $KEY_NAME already exists (using it; ensure you still have ${KEY_NAME}.pem)"
fi

# 2) Security group in the default VPC: SSH from your IP, 80/443 public
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region "$REGION" \
  --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
  --region "$REGION" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" \
    --description "DevLens alpha" --vpc-id "$VPC_ID" --region "$REGION" \
    --query 'GroupId' --output text)
  MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22  --cidr "${MYIP}/32"  --region "$REGION" >/dev/null
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80  --cidr 0.0.0.0/0     --region "$REGION" >/dev/null
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0     --region "$REGION" >/dev/null
  echo "Created SG $SG_ID (SSH from ${MYIP}/32; 80/443 open)"
else
  echo "Security group $SG_NAME already exists ($SG_ID)"
fi

# 3) Latest Ubuntu 24.04 LTS AMI (Canonical owner id 099720109477)
AMI_ID=$(aws ec2 describe-images --owners 099720109477 --region "$REGION" \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
echo "AMI: $AMI_ID"

# 4) Launch the instance with a gp3 root volume
INSTANCE_ID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${DISK_GB},\"VolumeType\":\"gp3\"}}]" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "Launched $INSTANCE_ID; waiting for running state..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

# 5) Static Elastic IP
ALLOC_ID=$(aws ec2 allocate-address --domain vpc --region "$REGION" --query 'AllocationId' --output text)
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --region "$REGION" >/dev/null
EIP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --region "$REGION" \
  --query 'Addresses[0].PublicIp' --output text)

cat <<EOF

============================================================
  Instance:   $INSTANCE_ID
  Elastic IP: $EIP
  SSH:        ssh -i ${KEY_NAME}.pem ubuntu@${EIP}
============================================================
Hostname (sslip.io, no DNS setup): ${EIP//./-}.sslip.io
Next:
  1) Set GitHub OAuth callback to https://${EIP//./-}.sslip.io/api/v1/auth/callback
  2) Copy the repo + your filled .env.prod to the box
  3) Run: bash deploy/bootstrap.sh
EOF
