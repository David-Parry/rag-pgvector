#!/usr/bin/env bash
# Query logs from rag namespace pods.
#
# Usage:
#   ./scripts/pod-logs.sh                       # follow question-api (last 200 lines + stream)
#   ./scripts/pod-logs.sh -F                    # one-shot: tail without following
#   ./scripts/pod-logs.sh -p                    # previous container (post-crash); implies -F
#   ./scripts/pod-logs.sh -t vectorizer         # pick a different deployment
#   ./scripts/pod-logs.sh -g 'redis|Redis'      # filter through grep -E
#   ./scripts/pod-logs.sh -l                    # list pods and exit
#   ./scripts/pod-logs.sh -t question-api -n 500 -g ERROR -p
#
# Flags:
#   -t TARGET   Deployment short-name or pod name (default: question-api).
#               Short names get the rag- prefix added (question-api -> rag-question-api).
#               If the value matches an existing pod exactly, it is used as-is.
#   -n LINES    --tail value (default: 200; use 'all' for full history)
#   -F          Disable follow (default is to follow)
#   -p          --previous (logs from the last terminated container — use after a crash).
#               Disables follow automatically (previous containers are not streamable).
#   -g PATTERN  Pipe output through `grep -E PATTERN` (case-insensitive)
#   -N NS       Namespace (default: rag)
#   -l          List rag-namespace pods and exit
#   -h          Help
set -euo pipefail

NAMESPACE="${NAMESPACE:-rag}"
TARGET="question-api"
LINES="200"
FOLLOW=1
PREVIOUS=0
PATTERN=""
LIST_ONLY=0

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'
  exit "${1:-0}"
}

while getopts ":t:n:Fpg:N:lh" opt; do
  case "$opt" in
    t) TARGET="$OPTARG" ;;
    n) LINES="$OPTARG" ;;
    F) FOLLOW=0 ;;
    p) PREVIOUS=1; FOLLOW=0 ;;
    g) PATTERN="$OPTARG" ;;
    N) NAMESPACE="$OPTARG" ;;
    l) LIST_ONLY=1 ;;
    h) usage 0 ;;
    \?) echo "Unknown flag: -$OPTARG" >&2; usage 1 ;;
    :)  echo "Flag -$OPTARG needs a value" >&2; usage 1 ;;
  esac
done

if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed." >&2
  exit 1
fi

if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "ERROR: namespace '$NAMESPACE' does not exist." >&2
  exit 1
fi

if (( LIST_ONLY )); then
  kubectl -n "$NAMESPACE" get pods -o wide
  exit 0
fi

# Resolve TARGET: if it matches a pod exactly, use the pod. Otherwise treat it
# as a deployment short-name and prepend rag- if missing.
RESOURCE=""
if kubectl -n "$NAMESPACE" get pod "$TARGET" >/dev/null 2>&1; then
  RESOURCE="pod/$TARGET"
else
  deploy="$TARGET"
  [[ "$deploy" != rag-* ]] && deploy="rag-$deploy"
  if ! kubectl -n "$NAMESPACE" get deploy "$deploy" >/dev/null 2>&1; then
    echo "ERROR: no pod '$TARGET' and no deployment '$deploy' in namespace '$NAMESPACE'." >&2
    echo "Available pods:" >&2
    kubectl -n "$NAMESPACE" get pods >&2 || true
    exit 1
  fi
  RESOURCE="deploy/$deploy"
fi

ARGS=(-n "$NAMESPACE" logs "$RESOURCE")
if [[ "$LINES" == "all" ]]; then
  ARGS+=(--tail=-1)
else
  ARGS+=(--tail="$LINES")
fi
(( FOLLOW ))   && ARGS+=(-f)
(( PREVIOUS )) && ARGS+=(--previous)

echo "==> kubectl ${ARGS[*]}${PATTERN:+ | grep -Ei '$PATTERN'}" >&2

if [[ -n "$PATTERN" ]]; then
  kubectl "${ARGS[@]}" 2>&1 | grep -Ei --line-buffered "$PATTERN"
else
  kubectl "${ARGS[@]}"
fi
