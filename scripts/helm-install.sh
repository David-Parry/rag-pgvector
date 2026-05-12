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

if ! command -v helm >/dev/null 2>&1; then
  echo "ERROR: helm is not installed. Install with: brew install helm" >&2
  exit 1
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
  --set "aws.auth.mode=${AWS_AUTH_MODE:-bearer}"
  --set-string "aws.auth.bearerToken=${AWS_BEARER_TOKEN_BEDROCK:-}"
  --set-string "aws.auth.accessKeyId=${AWS_ACCESS_KEY_ID:-}"
  --set-string "aws.auth.secretAccessKey=${AWS_SECRET_ACCESS_KEY:-}"
  --set "bedrock.region=${AWS_REGION:-us-east-1}"
  --set-string "bedrock.embeddingModelId=${BEDROCK_EMBEDDING_MODEL_ID:-amazon.titan-embed-text-v2:0}"
  --set "bedrock.embeddingDimensions=${BEDROCK_EMBEDDING_DIMENSIONS:-1024}"
  --set-string "govinfo.apiKey=${GOVINFO_API_KEY:-}"
  --set-string "govinfo.baseUrl=${GOVINFO_BASE_URL:-https://api.govinfo.gov}"
  --set-string "anthropic.apiKey=${ANTHROPIC_API_KEY:-}"
  --set "anthropic.model=${ANTHROPIC_MODEL:-claude-sonnet-4-5}"
  --set "qa.llmProvider=${LLM_PROVIDER:-anthropic}"
  --set "qa.ollamaBaseUrl=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
  --set "qa.ollamaModel=${OLLAMA_MODEL:-llama3.1:8b}"
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

echo "helm ${ARGS[*]}"
helm "${ARGS[@]}"

cat <<EOF

Release '$RELEASE' installed in namespace '$NAMESPACE'.
Run: bash scripts/port-forward.sh
EOF
