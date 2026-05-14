#!/usr/bin/env bash
# Verify Docker Desktop's built-in Kubernetes is enabled and reachable, then
# build the three local images on the Docker Desktop daemon.
#
# Docker Desktop's Kubernetes shares the daemon's image store, so a plain
# `docker build` is enough — no `kind load` or registry push is required.
#
# Prerequisite: enable Kubernetes in Docker Desktop:
#   Docker Desktop -> Settings -> Kubernetes -> Enable Kubernetes -> Apply & restart
set -euo pipefail

NAMESPACE="${NAMESPACE:-rag}"
TAG="${TAG:-0.1.0}"
KUBE_CONTEXT="${KUBE_CONTEXT:-docker-desktop}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
GENERATED_CA_BUNDLE=""
cleanup() {
  if [[ -n "$GENERATED_CA_BUNDLE" ]]; then
    rm -f "$GENERATED_CA_BUNDLE"
  fi
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed (Docker Desktop required)." >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed. Install with: brew install kubectl" >&2
  exit 1
fi

PY_APP_BUILD_ARGS=()

add_secret_file() {
  local env_name="$1"
  local secret_id="$2"
  local file_path="${!env_name:-}"

  if [[ -z "$file_path" ]]; then
    return
  fi
  if [[ ! -f "$file_path" ]]; then
    echo "ERROR: $env_name does not point to a readable file: $file_path" >&2
    exit 1
  fi

  export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
  PY_APP_BUILD_ARGS+=(--secret "id=${secret_id},src=${file_path}")
}

PIP_INDEX_BUILD_ARG="${RAG_DOCKER_PIP_INDEX_URL:-${RAG_DOCKER_UV_DEFAULT_INDEX:-}}"
if [[ -n "${PIP_INDEX_BUILD_ARG}" ]]; then
  PY_APP_BUILD_ARGS+=(--build-arg "PIP_INDEX_URL=${PIP_INDEX_BUILD_ARG}")
fi
add_secret_file RAG_PIP_INDEX_URL_FILE pip_index_url
add_secret_file RAG_UV_DEFAULT_INDEX_FILE uv_default_index
add_secret_file RAG_DOCKER_NETRC_FILE netrc
add_secret_file RAG_DOCKER_PIP_CONFIG_FILE pip_config

if [[ -z "${RAG_DOCKER_SSL_CERT_BUNDLE_FILE:-}" && "$(uname -s)" == "Darwin" && "$(command -v security || true)" ]]; then
  GENERATED_CA_BUNDLE="$(mktemp "${TMPDIR:-/tmp}/rag-docker-ca-bundle.XXXXXX.pem")"
  KEYCHAINS=()
  for keychain in \
    /System/Library/Keychains/SystemRootCertificates.keychain \
    /Library/Keychains/System.keychain \
    "$HOME"/Library/Keychains/login.keychain-db \
    "$HOME"/Library/Keychains/*.keychain-db \
    "$HOME"/Library/Keychains/*.keychain; do
    if [[ -f "$keychain" ]]; then
      KEYCHAINS+=("$keychain")
    fi
  done
  if [[ "${#KEYCHAINS[@]}" -gt 0 ]]; then
    security find-certificate -a -p "${KEYCHAINS[@]}" >"$GENERATED_CA_BUNDLE" 2>/dev/null || true
  fi
  if [[ -s "$GENERATED_CA_BUNDLE" ]]; then
    RAG_DOCKER_SSL_CERT_BUNDLE_FILE="$GENERATED_CA_BUNDLE"
  else
    rm -f "$GENERATED_CA_BUNDLE"
    GENERATED_CA_BUNDLE=""
  fi
fi
add_secret_file RAG_DOCKER_SSL_CERT_BUNDLE_FILE ssl_cert_bundle

echo "Checking Docker Desktop Kubernetes context..."
if ! kubectl config get-contexts -o name | grep -qx "$KUBE_CONTEXT"; then
  cat <<EOF >&2
ERROR: kube context '$KUBE_CONTEXT' was not found.

Enable Kubernetes in Docker Desktop:
  Docker Desktop -> Settings -> Kubernetes -> Enable Kubernetes -> Apply & restart

Then re-run this script.
EOF
  exit 1
fi

kubectl config use-context "$KUBE_CONTEXT" >/dev/null

if ! kubectl version --request-timeout=5s >/dev/null 2>&1; then
  echo "ERROR: cannot reach the '$KUBE_CONTEXT' API server. Is Docker Desktop running?" >&2
  exit 1
fi

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || \
  kubectl create namespace "$NAMESPACE"

echo
echo "Building rag-pgvector/postgres:17 ..."
docker build -t "rag-pgvector/postgres:17" "$ROOT_DIR/infra/docker/postgres-pgvector"

echo
echo "Building rag-pgvector/vectorizer:${TAG} ..."
docker build "${PY_APP_BUILD_ARGS[@]}" -t "rag-pgvector/vectorizer:${TAG}" -f "$ROOT_DIR/vectorizer/Dockerfile" "$ROOT_DIR"

echo
echo "Building rag-pgvector/question-api:${TAG} ..."
docker build "${PY_APP_BUILD_ARGS[@]}" -t "rag-pgvector/question-api:${TAG}" -f "$ROOT_DIR/question-api/Dockerfile" "$ROOT_DIR"

cat <<EOF

Cluster ready (Docker Desktop Kubernetes).
  context:    $KUBE_CONTEXT
  namespace:  $NAMESPACE
  images:     rag-pgvector/postgres:17, rag-pgvector/vectorizer:${TAG}, rag-pgvector/question-api:${TAG}

Docker Desktop Kubernetes shares the Docker daemon, so these images are visible
to the cluster without any push or load step.

Next: bash scripts/helm-install.sh
EOF
