#!/usr/bin/env bash
# Install / upgrade the rag-pgvector chart against the current kube context.
# Reads .env (if present) and forwards the relevant secrets as --set values.
set -euo pipefail

RELEASE="${RELEASE:-rag}"
NAMESPACE="${NAMESPACE:-rag}"
TAG="${TAG:-0.1.0}"
VALUES_FILE="${VALUES_FILE:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  ANTHROPIC_KEY_FILE="${ANTHROPIC_API_KEY_FILE:-$ROOT_DIR/claudeapi.txt}"
  if [[ -f "$ANTHROPIC_KEY_FILE" ]]; then
    ANTHROPIC_API_KEY="$(tr -d '\r\n' < "$ANTHROPIC_KEY_FILE")"
    export ANTHROPIC_API_KEY
  fi
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "ERROR: helm is not installed. Install with: brew install helm" >&2
  exit 1
fi

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

has_real_bedrock_bearer_token() {
  [[ -n "${AWS_BEARER_TOKEN_BEDROCK:-}" ]] \
    && [[ "${AWS_BEARER_TOKEN_BEDROCK}" != "replace-with-embedding-account-bedrock-api-key" ]] \
    && [[ "${AWS_BEARER_TOKEN_BEDROCK}" != "replace-with-bedrock-api-key" ]]
}

has_real_govinfo_api_key() {
  [[ -n "${GOVINFO_API_KEY:-}" ]] \
    && [[ "${GOVINFO_API_KEY}" != "replace-with-govinfo-api-key" ]]
}

INTERNAL_NETWORK=0
if is_truthy "${RAG_INTERNAL_NETWORK:-}" || is_truthy "${RAG_ON_PREM:-}" || is_truthy "${ON_PREM:-}"; then
  INTERNAL_NETWORK=1
fi

AWS_AUTH_MODE_RESOLVED="${AWS_AUTH_MODE:-}"
if [[ -z "$AWS_AUTH_MODE_RESOLVED" ]]; then
  if has_real_bedrock_bearer_token; then
    AWS_AUTH_MODE_RESOLVED="bearer"
  elif [[ -n "${AWS_ACCESS_KEY_ID:-}" || -n "${AWS_SECRET_ACCESS_KEY:-}" || -n "${AWS_PROFILE:-${AWS_DEFAULT_PROFILE:-}}" ]] \
    || { (( ! INTERNAL_NETWORK )) && command -v aws >/dev/null 2>&1; }; then
    AWS_AUTH_MODE_RESOLVED="accessKey"
  elif (( INTERNAL_NETWORK )); then
    AWS_AUTH_MODE_RESOLVED="none"
  else
    cat >&2 <<EOF
ERROR: Bedrock embedding credentials are required outside the internal/on-prem network.

Set one of:
  - AWS_BEARER_TOKEN_BEDROCK in .env
  - AWS_PROFILE / AWS_DEFAULT_PROFILE for an AWS CLI profile
  - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

For an internal/on-prem install that intentionally does not inject AWS credentials:
  RAG_INTERNAL_NETWORK=1 bash scripts/helm-install.sh
EOF
    exit 1
  fi
fi

if [[ "$AWS_AUTH_MODE_RESOLVED" == "accessKey" && ( -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ) ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: aws CLI is required to export profile/session credentials for aws.auth.mode=accessKey." >&2
    exit 1
  fi
  PROFILE_ARGS=()
  if [[ -n "${AWS_PROFILE:-${AWS_DEFAULT_PROFILE:-}}" ]]; then
    PROFILE_ARGS=(--profile "${AWS_PROFILE:-${AWS_DEFAULT_PROFILE:-}}")
  fi
  eval "$(aws configure export-credentials --format env-no-export "${PROFILE_ARGS[@]}")"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
fi

BEDROCK_BEARER_TOKEN_VALUE=""
if has_real_bedrock_bearer_token; then
  BEDROCK_BEARER_TOKEN_VALUE="$AWS_BEARER_TOKEN_BEDROCK"
fi
GOVINFO_API_KEY_VALUE="DEMO_KEY"
if has_real_govinfo_api_key; then
  GOVINFO_API_KEY_VALUE="$GOVINFO_API_KEY"
fi
NOVA_SONIC_MODEL_ID="${BEDROCK_NOVA_SONIC_MODEL_ID:-${NOVA_SONIC_MODEL:-amazon.nova-2-sonic-v1:0}}"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || \
  kubectl create namespace "$NAMESPACE"

ARGS=(
  upgrade --install "$RELEASE"
  "$ROOT_DIR/infra/helm/rag-pgvector"
  --namespace "$NAMESPACE"
  --create-namespace
  --set "fullnameOverride=rag"
  --set "image.tag=${TAG}"
  --set "aws.auth.mode=${AWS_AUTH_MODE_RESOLVED}"
  --set-string "aws.auth.bearerToken=${BEDROCK_BEARER_TOKEN_VALUE}"
  --set-string "aws.auth.accessKeyId=${AWS_ACCESS_KEY_ID:-}"
  --set-string "aws.auth.secretAccessKey=${AWS_SECRET_ACCESS_KEY:-}"
  --set-string "aws.auth.sessionToken=${AWS_SESSION_TOKEN:-}"
  --set "bedrock.region=${AWS_REGION:-us-east-1}"
  --set-string "bedrock.embeddingModelId=${EMBEDDING_MODEL:-${BEDROCK_EMBEDDING_MODEL_ID:-amazon.titan-embed-text-v2:0}}"
  --set-string "bedrock.embeddingBearerToken=${BEDROCK_BEARER_TOKEN_VALUE}"
  --set "bedrock.embeddingDimensions=${BEDROCK_EMBEDDING_DIMENSIONS:-1024}"
  --set-string "novaSonic.modelId=${NOVA_SONIC_MODEL_ID}"
  --set-string "novaSonic.roleArn=${SONIC_AWS_ROLE_ARN:-}"
  --set-string "novaSonic.accessKeyId=${SONIC_AWS_ACCESS_KEY_ID:-}"
  --set-string "novaSonic.secretAccessKey=${SONIC_AWS_SECRET_ACCESS_KEY:-}"
  --set-string "novaSonic.sessionToken=${SONIC_AWS_SESSION_TOKEN:-}"
  --set-string "novaSonic.credentialExpiration=${SONIC_AWS_CREDENTIAL_EXPIRATION:-}"
  --set-string "anthropic.apiKey=${ANTHROPIC_API_KEY:-}"
  --set-string "anthropic.model=${ANTHROPIC_DIRECT_MODEL:-claude-sonnet-4-5}"
  --set "anthropic.maxTokens=${ANTHROPIC_MAX_TOKENS:-1024}"
  --set "anthropic.temperature=${ANTHROPIC_TEMPERATURE:-0.0}"
  --set "anthropic.timeoutSeconds=${ANTHROPIC_TIMEOUT_SECONDS:-90}"
  --set-string "govinfo.apiKey=${GOVINFO_API_KEY_VALUE}"
  --set-string "govinfo.baseUrl=${GOVINFO_BASE_URL:-https://api.govinfo.gov}"
  --set-string "vectorizer.env.LOG_LEVEL=${LOG_LEVEL:-DEBUG}"
  --set-string "vectorizer.env.LOG_FORMAT=${LOG_FORMAT:-json}"
  --set-string "qa.env.LOG_LEVEL=${LOG_LEVEL:-DEBUG}"
  --set-string "qa.env.LOG_FORMAT=${LOG_FORMAT:-json}"
  --set-string "qa.env.VOICE_ENABLED=${VOICE_ENABLED:-true}"
  --set-string "qa.env.NOVA_SONIC_VOICE=${NOVA_SONIC_VOICE:-matthew}"
  --set-string "qa.env.NOVA_SONIC_ENDPOINTING_SENSITIVITY=${NOVA_SONIC_ENDPOINTING_SENSITIVITY:-MEDIUM}"
  --wait
  --timeout 5m
)

if [[ -n "$VALUES_FILE" ]]; then
  ARGS+=(-f "$VALUES_FILE")
fi

echo "helm upgrade --install $RELEASE <chart> --namespace $NAMESPACE --set image.tag=${TAG} --wait --timeout 5m"
helm "${ARGS[@]}"

cat <<EOF

Release '$RELEASE' installed in namespace '$NAMESPACE'.
Run: bash scripts/port-forward.sh
EOF
