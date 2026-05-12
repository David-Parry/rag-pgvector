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

AWS_AUTH_MODE_RESOLVED="${AWS_AUTH_MODE:-}"
if [[ -z "$AWS_AUTH_MODE_RESOLVED" ]]; then
  AWS_AUTH_MODE_RESOLVED="bearer"
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
  --set-string "aws.auth.bearerToken=${AWS_BEARER_TOKEN_BEDROCK:-}"
  --set-string "aws.auth.accessKeyId=${AWS_ACCESS_KEY_ID:-}"
  --set-string "aws.auth.secretAccessKey=${AWS_SECRET_ACCESS_KEY:-}"
  --set-string "aws.auth.sessionToken=${AWS_SESSION_TOKEN:-}"
  --set "bedrock.region=${AWS_REGION:-us-east-1}"
  --set-string "bedrock.embeddingModelId=${EMBEDDING_MODEL:-${BEDROCK_EMBEDDING_MODEL_ID:-amazon.titan-embed-text-v2:0}}"
  --set-string "bedrock.embeddingBearerToken=${AWS_BEARER_TOKEN_BEDROCK:-}"
  --set "bedrock.embeddingDimensions=${BEDROCK_EMBEDDING_DIMENSIONS:-1024}"
  --set-string "anthropic.apiKey=${ANTHROPIC_API_KEY:-}"
  --set-string "anthropic.model=${ANTHROPIC_DIRECT_MODEL:-claude-sonnet-4-5}"
  --set-string "govinfo.apiKey=${GOVINFO_API_KEY:-}"
  --set-string "govinfo.baseUrl=${GOVINFO_BASE_URL:-https://api.govinfo.gov}"
  --set-string "vectorizer.env.LOG_LEVEL=${LOG_LEVEL:-DEBUG}"
  --set-string "vectorizer.env.LOG_FORMAT=${LOG_FORMAT:-json}"
  --set-string "qa.env.LOG_LEVEL=${LOG_LEVEL:-DEBUG}"
  --set-string "qa.env.LOG_FORMAT=${LOG_FORMAT:-json}"
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
