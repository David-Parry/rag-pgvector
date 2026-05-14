#!/usr/bin/env bash
# Verify a Nova Sonic STS federated session: identity, remaining lifetime,
# and Bedrock permission for the Nova Sonic model.
#
# Usage: ./check_nova_sonic.sh [path/to/env-file]
#        Defaults to ./env.nova-sonic-sts

set -u

ENV_FILE="${1:-./env.nova-sonic-sts}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2
  exit 2
fi

# Load env file into this shell.
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

REGION="${AWS_REGION:-us-east-1}"
MODEL_ID="${BEDROCK_NOVA_SONIC_MODEL_ID:-amazon.nova-sonic-v1:0}"

echo "== STS identity =="
if ! aws sts get-caller-identity --output json; then
  echo "STS call failed — credentials are invalid or expired." >&2
  exit 1
fi

echo
echo "== Session lifetime =="
if [[ -n "${SONIC_AWS_CREDENTIAL_EXPIRATION:-}" ]]; then
  EXP_EPOCH=$(date -j -f "%Y-%m-%dT%H:%M:%S%z" \
    "${SONIC_AWS_CREDENTIAL_EXPIRATION/+00:00/+0000}" "+%s" 2>/dev/null \
    || date -d "${SONIC_AWS_CREDENTIAL_EXPIRATION}" "+%s" 2>/dev/null)
  NOW_EPOCH=$(date "+%s")
  if [[ -n "${EXP_EPOCH:-}" ]]; then
    REMAIN=$(( EXP_EPOCH - NOW_EPOCH ))
    if (( REMAIN > 0 )); then
      H=$(( REMAIN / 3600 ))
      M=$(( (REMAIN % 3600) / 60 ))
      echo "expires:   $SONIC_AWS_CREDENTIAL_EXPIRATION"
      echo "remaining: ${H}h ${M}m"
    else
      echo "expired at $SONIC_AWS_CREDENTIAL_EXPIRATION"
    fi
  else
    echo "expires: $SONIC_AWS_CREDENTIAL_EXPIRATION (could not parse for delta)"
  fi
else
  echo "SONIC_AWS_CREDENTIAL_EXPIRATION not set in env file"
fi

echo
echo "== Bedrock permission probe ($MODEL_ID, $REGION) =="
# Nova Sonic only supports InvokeModelWithBidirectionalStream, so a regular
# invoke-model call will never succeed. The *type* of error tells us about
# auth/permissions:
#   AccessDeniedException  -> creds valid, but no bedrock:InvokeModel perm
#   ValidationException    -> creds + perm OK, model just rejects the API shape
#   ExpiredTokenException  -> creds dead
TMP_OUT=$(mktemp)
TMP_ERR=$(mktemp)
trap 'rm -f "$TMP_OUT" "$TMP_ERR"' EXIT

aws bedrock-runtime invoke-model \
  --region "$REGION" \
  --model-id "$MODEL_ID" \
  --content-type application/json \
  --accept application/json \
  --cli-binary-format raw-in-base64-out \
  --body '{"ping":1}' \
  "$TMP_OUT" \
  >/dev/null 2>"$TMP_ERR"
RC=$?

ERR_TEXT=$(cat "$TMP_ERR")

if (( RC == 0 )); then
  echo "unexpected success — Nova Sonic accepted a plain invoke-model call?"
  cat "$TMP_OUT"
  exit 0
fi

if   grep -q "ExpiredTokenException\|InvalidClientTokenId\|TokenRefreshRequired" <<<"$ERR_TEXT"; then
  echo "RESULT: credentials are dead (expired/invalid)."
  echo "$ERR_TEXT"
  exit 1
elif grep -q "AccessDeniedException\|not authorized" <<<"$ERR_TEXT"; then
  # AccessDenied here only proves no InvokeModel perm — bidirectional may still work.
  echo "RESULT: credentials valid, but principal lacks bedrock:InvokeModel on this model."
  echo "       (This does NOT rule out bedrock:InvokeModelWithBidirectionalStream — the"
  echo "        BedrockNovaSonicOnly role is likely scoped to the bidirectional action only.)"
  echo
  echo "$ERR_TEXT"
  exit 0
elif grep -q "ValidationException\|bidirectional\|only supports" <<<"$ERR_TEXT"; then
  echo "RESULT: credentials + Bedrock model access OK."
  echo "       (Model rejected the non-streaming API shape, which is expected.)"
  echo
  echo "$ERR_TEXT"
  exit 0
else
  echo "RESULT: unrecognized error — review below."
  echo "$ERR_TEXT"
  exit 1
fi
