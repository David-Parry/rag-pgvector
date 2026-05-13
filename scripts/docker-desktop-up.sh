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

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed (Docker Desktop required)." >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed. Install with: brew install kubectl" >&2
  exit 1
fi

SERVICE_BUILD_ARGS=()
if [[ -n "$CUSTOM_CA_CERT" ]]; then
  if [[ ! -f "$CUSTOM_CA_CERT" ]]; then
    echo "ERROR: CUSTOM_CA_CERT does not point to a readable file: $CUSTOM_CA_CERT" >&2
    exit 1
  fi
  export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
  SERVICE_BUILD_ARGS+=(--secret "id=custom_ca,src=${CUSTOM_CA_CERT}")
fi

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
docker build "${PY_APP_BUILD_ARGS[@]} ${SERVICE_BUILD_ARGS[@]}" -t "rag-pgvector/vectorizer:${TAG}" -f "$ROOT_DIR/vectorizer/Dockerfile" "$ROOT_DIR"

echo
echo "Building rag-pgvector/question-api:${TAG} ..."
docker build "${PY_APP_BUILD_ARGS[@]} ${SERVICE_BUILD_ARGS[@]}" -t "rag-pgvector/question-api:${TAG}" -f "$ROOT_DIR/question-api/Dockerfile" "$ROOT_DIR"

cat <<EOF

Cluster ready (Docker Desktop Kubernetes).
  context:    $KUBE_CONTEXT
  namespace:  $NAMESPACE
  images:     rag-pgvector/postgres:17, rag-pgvector/vectorizer:${TAG}, rag-pgvector/question-api:${TAG}

Docker Desktop Kubernetes shares the Docker daemon, so these images are visible
to the cluster without any push or load step.

Next: bash scripts/helm-install.sh
EOF
