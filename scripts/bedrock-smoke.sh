#!/usr/bin/env bash
#
# Smoke-test the Bedrock API key in .env by embedding a short input with
# EMBEDDING_MODEL and printing the vector dimensions, a few
# sample values, and the input token count.
#
# Usage:
#   ./scripts/bedrock-smoke.sh                       # embeds "hello bedrock test"
#   ./scripts/bedrock-smoke.sh "any three words"     # embeds your own text
#   FULL_VECTOR=1 ./scripts/bedrock-smoke.sh         # also dumps the full 1024-dim vector
#
# The script deliberately unsets AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
# AWS_SESSION_TOKEN / AWS_PROFILE so the call is forced through
# AWS_BEARER_TOKEN_BEDROCK and we know we're testing the right credential.
#
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
INPUT_TEXT="${1:-hello bedrock test}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "missing ${ENV_FILE}" >&2
  exit 1
fi

# Load .env into the environment (export every assigned var).
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Force the call through the bearer token by clearing any other AWS creds.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE

if [ -z "${AWS_BEARER_TOKEN_BEDROCK:-}" ] \
   || [ "${AWS_BEARER_TOKEN_BEDROCK}" = "replace-with-bedrock-api-key" ]; then
  echo "AWS_BEARER_TOKEN_BEDROCK is not set in ${ENV_FILE}" >&2
  exit 1
fi

REGION="${AWS_REGION:-us-east-1}"
MODEL_ID="${EMBEDDING_MODEL:-${BEDROCK_EMBEDDING_MODEL_ID:-amazon.titan-embed-text-v2:0}}"

printf '[bedrock-smoke] region=%s model=%s input=%q\n' \
  "${REGION}" "${MODEL_ID}" "${INPUT_TEXT}"

# Build the request body as JSON so jq -R handles quoting/escaping for us.
BODY="$(jq -nc --arg t "${INPUT_TEXT}" '{inputText:$t}')"

OUT="$(mktemp)"
trap 'rm -f "${OUT}"' EXIT

aws bedrock-runtime invoke-model \
  --region "${REGION}" \
  --model-id "${MODEL_ID}" \
  --content-type application/json \
  --accept application/json \
  --cli-binary-format raw-in-base64-out \
  --body "${BODY}" \
  "${OUT}" >/dev/null

if [ "${FULL_VECTOR:-0}" = "1" ]; then
  jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, embedding:.embedding}' "${OUT}"
else
  jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, first5:.embedding[0:5]}' "${OUT}"
fi
