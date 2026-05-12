#!/usr/bin/env bash
#
# Tear down the rag-pgvector deployment from the local Kubernetes cluster.
#
# This is the inverse of `helm-install.sh`. It performs a clean wipe so the
# next install starts from a fresh database (handy when the pgvector schema
# has changed and the existing `rag_chunks` table is incompatible — e.g. when
# renaming columns or adding hoisted metadata columns, since
# `ainit_vectorstore_table` is no-op when the table already exists).
#
# Order of operations:
#   1. Reap any leftover `kubectl port-forward` processes from this user that
#      were targeting our services (otherwise `kubectl delete namespace`
#      hangs on terminating endpoints).
#   2. `helm uninstall` (waits for resources to drain).
#   3. Delete StatefulSet PVCs explicitly — `helm uninstall` does NOT clean
#      these up because they're managed by the StatefulSet's
#      volumeClaimTemplates, not by Helm.
#   4. Delete the namespace as a catch-all and wait until the API server
#      reports it gone.
#   5. Verify nothing remains under the namespace.
#
# Usage:
#   ./scripts/teardown.sh
#   RELEASE=rag NAMESPACE=rag ./scripts/teardown.sh
#   KEEP_NAMESPACE=1 ./scripts/teardown.sh    # uninstall release but keep ns
#
# Env vars:
#   RELEASE          (default: rag)
#   NAMESPACE        (default: rag)
#   KEEP_NAMESPACE   (default: 0)  set to 1 to keep the namespace
set -euo pipefail

RELEASE="${RELEASE:-rag}"
NAMESPACE="${NAMESPACE:-rag}"
KEEP_NAMESPACE="${KEEP_NAMESPACE:-0}"

if ! command -v helm >/dev/null 2>&1; then
  echo "ERROR: helm is not installed." >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed." >&2
  exit 1
fi

# 1. Reap stale port-forwards targeting our services so the namespace can
#    actually drain. We kill broadly here because by the time the user runs
#    teardown, there's no scenario where they'd want a port-forward to live.
STALE="$(pgrep -u "$(id -u)" -f \
  "kubectl .*(-n|--namespace)[= ]+${NAMESPACE} .*port-forward" \
  2>/dev/null || true)"
if [[ -n "${STALE}" ]]; then
  echo "Killing kubectl port-forward processes targeting ${NAMESPACE}: ${STALE//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${STALE} 2>/dev/null || true
  sleep 1
  LEFT="$(pgrep -u "$(id -u)" -f \
    "kubectl .*(-n|--namespace)[= ]+${NAMESPACE} .*port-forward" \
    2>/dev/null || true)"
  if [[ -n "${LEFT}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${LEFT} 2>/dev/null || true
  fi
fi

# 2. Uninstall the helm release if present.
if helm status "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "helm uninstall ${RELEASE} -n ${NAMESPACE}"
  helm uninstall "${RELEASE}" -n "${NAMESPACE}" --wait --timeout 3m
else
  echo "helm release '${RELEASE}' not found in namespace '${NAMESPACE}' (skipping)"
fi

# 3. Delete StatefulSet PVCs. These outlive `helm uninstall` because they're
#    owned by the StatefulSet's volumeClaimTemplates, not the Helm release.
#    Without this step the next install reuses the old DB volume — which is
#    exactly what we DON'T want when the schema changed.
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  PVCS="$(kubectl -n "${NAMESPACE}" get pvc -o name 2>/dev/null || true)"
  if [[ -n "${PVCS}" ]]; then
    echo "Deleting PVCs in ${NAMESPACE}:"
    echo "${PVCS}" | sed 's/^/  /'
    # shellcheck disable=SC2086
    kubectl -n "${NAMESPACE}" delete ${PVCS} --wait=true --timeout=2m
  else
    echo "No PVCs found in ${NAMESPACE}."
  fi
fi

# 4. Delete the namespace (catches anything we missed: ConfigMaps, Secrets,
#    leftover Pods stuck Terminating, etc).
if [[ "${KEEP_NAMESPACE}" == "1" ]]; then
  echo "KEEP_NAMESPACE=1 — leaving namespace '${NAMESPACE}' in place."
else
  if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    echo "kubectl delete namespace ${NAMESPACE}"
    kubectl delete namespace "${NAMESPACE}" --wait=true --timeout=3m
  else
    echo "namespace '${NAMESPACE}' already gone."
  fi

  # Belt-and-suspenders wait loop — `--wait=true` should already block, but
  # finalizers occasionally leave it in a Terminating limbo we want to surface.
  for _ in $(seq 1 30); do
    kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || break
    echo "  waiting for namespace '${NAMESPACE}' to terminate..."
    sleep 2
  done
  if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    echo "WARNING: namespace '${NAMESPACE}' is still present (likely stuck on a finalizer)." >&2
    kubectl get namespace "${NAMESPACE}" -o yaml | grep -E '^\s*finalizers:' -A 5 >&2 || true
    exit 1
  fi
fi

# 5. Verify.
echo
echo "Verification:"
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "  namespace '${NAMESPACE}' still present (KEEP_NAMESPACE=${KEEP_NAMESPACE}):"
  kubectl -n "${NAMESPACE}" get all,pvc,secrets,configmaps 2>/dev/null | sed 's/^/    /' || true
else
  echo "  namespace '${NAMESPACE}' is gone."
fi
if helm status "${RELEASE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "  WARNING: helm release '${RELEASE}' still reports as present." >&2
  exit 1
else
  echo "  helm release '${RELEASE}' is gone."
fi

cat <<EOF

Teardown complete.
Re-deploy with:
  bash scripts/docker-desktop-up.sh   # rebuilds local images
  bash scripts/helm-install.sh
EOF
