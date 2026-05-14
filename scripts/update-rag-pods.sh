#!/usr/bin/env bash
# Update existing rag-pgvector Kubernetes pods without teardown.
#
# This rebuilds local images, runs Helm upgrade in place, and rollout-restarts
# selected application Deployments. It does not uninstall Helm, delete PVCs, or
# delete the namespace.
set -euo pipefail

NAMESPACE="${NAMESPACE:-rag}"
RELEASE="${RELEASE:-rag}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-300s}"
UPDATE_COMPONENTS="${UPDATE_COMPONENTS:-question-api}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

restart_component_deployments() {
  local component="$1"
  local selector="app.kubernetes.io/component=${component}"
  local deployments
  deployments="$(kubectl get deploy -n "$NAMESPACE" -l "$selector" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null || true)"

  if [[ -z "$deployments" ]]; then
    echo "WARNING: no Deployment found for component '$component' in namespace '$NAMESPACE'." >&2
    return
  fi

  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    echo "Rolling deployment/$name in namespace $NAMESPACE ..."
    kubectl rollout restart "deployment/$name" -n "$NAMESPACE"
    kubectl rollout status "deployment/$name" -n "$NAMESPACE" "--timeout=$ROLLOUT_TIMEOUT"
  done <<<"$deployments"
}

cat <<EOF
Updating rag-pgvector pods in place.
  release:    $RELEASE
  namespace:  $NAMESPACE
  components: $UPDATE_COMPONENTS

This does NOT run teardown, uninstall Helm, delete PVCs, or delete the namespace.
EOF

if ! is_truthy "${UPDATE_SKIP_BUILD:-}"; then
  echo
  echo "Step 1/3: build/import local images"
  bash "$ROOT_DIR/scripts/docker-desktop-up.sh"
else
  echo "Step 1/3: skipped image build/import (UPDATE_SKIP_BUILD=1)"
fi

if ! is_truthy "${UPDATE_SKIP_HELM:-}"; then
  echo
  echo "Step 2/3: helm upgrade existing release"
  bash "$ROOT_DIR/scripts/helm-install.sh"
else
  echo "Step 2/3: skipped Helm upgrade (UPDATE_SKIP_HELM=1)"
fi

if ! is_truthy "${UPDATE_SKIP_ROLLOUT:-}"; then
  echo
  echo "Step 3/3: rollout restart updated Deployment(s)"
  IFS=',' read -r -a components <<<"$UPDATE_COMPONENTS"
  for component in "${components[@]}"; do
    component="$(echo "$component" | xargs)"
    [[ -n "$component" ]] || continue
    restart_component_deployments "$component"
  done
else
  echo "Step 3/3: skipped rollout restart (UPDATE_SKIP_ROLLOUT=1)"
fi

echo
echo "Update complete. Current pods:"
kubectl get pods -n "$NAMESPACE" -o wide
