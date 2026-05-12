#!/usr/bin/env bash
#
# Create a long-term Bedrock API key scoped to amazon.titan-embed-text-v2:0
# and write it to .env as AWS_BEARER_TOKEN_BEDROCK.
#
# Prereqs:
#   - AWS CLI v2 logged in as a principal with IAM + Bedrock admin rights
#   - amazon.titan-embed-text-v2:0 already enabled under
#     Bedrock -> Model access in the target region
#
# Usage:
#   ./scripts/bedrock-create-api-key.sh
#
# Override any of these via env vars if you want different values:
#   AWS_PROFILE, AWS_REGION, IAM_USER, POLICY_NAME, MODEL_ID,
#   CREDENTIAL_AGE_DAYS, ENV_FILE
#
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
IAM_USER="${IAM_USER:-bedrock-rag-pgvector-dev}"
POLICY_NAME="${POLICY_NAME:-BedrockInvokeTitanEmbedV2}"
MODEL_ID="${MODEL_ID:-amazon.titan-embed-text-v2:0}"
CREDENTIAL_AGE_DAYS="${CREDENTIAL_AGE_DAYS:-15}"
ENV_FILE="${ENV_FILE:-.env}"

export AWS_PROFILE AWS_REGION

log() { printf '\n\033[1;34m[bedrock-key]\033[0m %s\n' "$*"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
require aws
require jq

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
MODEL_ARN="arn:aws:bedrock:${AWS_REGION}::foundation-model/${MODEL_ID}"
log "account=${ACCOUNT_ID} region=${AWS_REGION} user=${IAM_USER}"
log "model_arn=${MODEL_ARN}"

# 1. Verify the model is visible in this region.
log "Checking ${MODEL_ID} is listed in ${AWS_REGION}..."
aws bedrock list-foundation-models \
  --region "${AWS_REGION}" \
  --query "modelSummaries[?modelId=='${MODEL_ID}'].modelId" \
  --output text | grep -q "${MODEL_ID}" \
  || { echo "model ${MODEL_ID} not listed in ${AWS_REGION}" >&2; exit 1; }

# 2. Create the dev IAM user (idempotent).
if aws iam get-user --user-name "${IAM_USER}" >/dev/null 2>&1; then
  log "IAM user ${IAM_USER} already exists, reusing"
else
  log "Creating IAM user ${IAM_USER}"
  aws iam create-user --user-name "${IAM_USER}" >/dev/null
fi

# 3. Attach the minimum-permission inline policy (replace if already present).
log "Putting inline policy ${POLICY_NAME}"
POLICY_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBearerTokenAuth",
      "Effect": "Allow",
      "Action": ["bedrock:CallWithBearerToken"],
      "Resource": "*"
    },
    {
      "Sid": "AllowInvokeTitanEmbedV2",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": ["${MODEL_ARN}"]
    }
  ]
}
JSON
)
aws iam put-user-policy \
  --user-name "${IAM_USER}" \
  --policy-name "${POLICY_NAME}" \
  --policy-document "${POLICY_DOC}"

# 4. Create the long-term Bedrock API key.
log "Creating Bedrock API key (expires in ${CREDENTIAL_AGE_DAYS} days)"
if ! KEY_JSON="$(aws iam create-service-specific-credential \
      --user-name "${IAM_USER}" \
      --service-name bedrock.amazonaws.com \
      --credential-age-days "${CREDENTIAL_AGE_DAYS}" 2>&1)"; then
  # Older CLI versions may not accept --credential-age-days; retry without it.
  if echo "${KEY_JSON}" | grep -qi 'credential-age-days\|Unknown options'; then
    log "CLI rejected --credential-age-days; retrying with default lifetime"
    KEY_JSON="$(aws iam create-service-specific-credential \
      --user-name "${IAM_USER}" \
      --service-name bedrock.amazonaws.com)"
  else
    echo "${KEY_JSON}" >&2
    exit 1
  fi
fi

BEARER_TOKEN="$(echo "${KEY_JSON}" | jq -r '
  .ServiceSpecificCredential.ServiceCredentialSecret
  // .ServiceSpecificCredential.ServicePassword
  // empty')"
KEY_ID="$(echo "${KEY_JSON}" | jq -r '
  .ServiceSpecificCredential.ServiceSpecificCredentialId
  // .ServiceSpecificCredential.ServiceCredentialAlias
  // empty')"
EXPIRES_ON="$(echo "${KEY_JSON}" | jq -r '
  .ServiceSpecificCredential.ExpirationDate // empty')"

if [ -z "${BEARER_TOKEN}" ]; then
  echo "could not extract bearer token; raw response follows:" >&2
  echo "${KEY_JSON}" >&2
  exit 1
fi
log "key_id=${KEY_ID} expires=${EXPIRES_ON}"

# 5. Write into .env (replace existing line or append).
log "Writing AWS_BEARER_TOKEN_BEDROCK into ${ENV_FILE}"
if [ -f "${ENV_FILE}" ] && grep -q '^AWS_BEARER_TOKEN_BEDROCK=' "${ENV_FILE}"; then
  sed -i.bak "s|^AWS_BEARER_TOKEN_BEDROCK=.*|AWS_BEARER_TOKEN_BEDROCK=${BEARER_TOKEN}|" "${ENV_FILE}"
  rm -f "${ENV_FILE}.bak"
else
  printf '\nAWS_BEARER_TOKEN_BEDROCK=%s\n' "${BEARER_TOKEN}" >> "${ENV_FILE}"
fi

# 6. Smoke-test the new key end-to-end.
log "Smoke-testing the new key against ${MODEL_ID}"
TMP_OUT="$(mktemp)"
trap 'rm -f "${TMP_OUT}"' EXIT
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
    -u AWS_SESSION_TOKEN -u AWS_PROFILE \
    AWS_BEARER_TOKEN_BEDROCK="${BEARER_TOKEN}" \
aws bedrock-runtime invoke-model \
  --region "${AWS_REGION}" \
  --model-id "${MODEL_ID}" \
  --content-type application/json \
  --accept application/json \
  --cli-binary-format raw-in-base64-out \
  --body '{"inputText":"hello bedrock test"}' \
  "${TMP_OUT}" >/dev/null

jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, first5:.embedding[0:5]}' "${TMP_OUT}"
log "done. ${ENV_FILE} now has AWS_BEARER_TOKEN_BEDROCK set."
