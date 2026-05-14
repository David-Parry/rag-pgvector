#!/usr/bin/env bash
# Forward app, database, and Redis Stack services to the laptop:
#   localhost:8001 -> svc/vectorizer:8000
#   localhost:8000 -> svc/question-api:8000
#   localhost:5432 -> svc/<release>-postgres:5432
#   localhost:6379 -> svc/<release>-redis-stack:6379
#
# Behavior:
#   * On startup, scans for stale `kubectl port-forward` processes that target
#     the same services in this namespace (typical when a previous shell exited
#     without firing its cleanup trap) and refuses to launch unless they're
#     reaped first. Set KILL_STALE=1 to auto-reap them.
#   * Pre-flight checks each local port with lsof and bails with a precise
#     "<port> held by <cmd> (PID N)" message instead of letting kubectl emit
#     "Listeners failed to create" errors.
#   * Ctrl-C (or any exit) terminates every kubectl this script spawned via
#     a PID-tracked cleanup trap.
#
# Env overrides:
#   NAMESPACE         (default: rag)
#   VECTORIZER_PORT   (default: 8001)
#   QA_PORT           (default: 8000)
#   POSTGRES_PORT     (default: 5432)
#   POSTGRES_SVC      (default: rag-postgres)
#   REDIS_PORT        (default: 6379)
#   REDIS_SVC         (default: rag-redis-stack)
#   KILL_STALE=1      auto-reap stale kubectl port-forwards from prior runs
set -euo pipefail

NAMESPACE="${NAMESPACE:-rag}"
VECTORIZER_PORT="${VECTORIZER_PORT:-8001}"
QA_PORT="${QA_PORT:-8000}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_SVC="${POSTGRES_SVC:-rag-postgres}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_SVC="${REDIS_SVC:-rag-redis-stack}"
KILL_STALE="${KILL_STALE:-0}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl is not installed." >&2
  exit 1
fi

# Track every kubectl PID we spawn so cleanup can kill exactly those, instead
# of relying on a pkill -P $$ pattern which silently misses re-parented kids.
PF_PIDS=()

cleanup() {
  trap - EXIT INT TERM
  local pid
  if (( ${#PF_PIDS[@]} > 0 )); then
    echo
    echo "Stopping port-forwards (${PF_PIDS[*]})..."
    for pid in "${PF_PIDS[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# --- stale-port-forward detection ---------------------------------------------
# Match this user's `kubectl ... -n <NAMESPACE> port-forward svc/<one of ours>`
# regardless of whose shell launched it (orphaned trees from past runs included).
stale_pf_pids() {
  pgrep -u "$(id -u)" -f \
    "kubectl .*(-n|--namespace)[= ]+${NAMESPACE} .*port-forward .*svc/(vectorizer|question-api|${POSTGRES_SVC}|${REDIS_SVC})" \
    2>/dev/null || true
}

STALE="$(stale_pf_pids)"
if [[ -n "${STALE}" ]]; then
  echo "Detected stale kubectl port-forwards from a previous run:"
  # shellcheck disable=SC2086
  ps -o pid,etime,command -p ${STALE} | sed '1d;s/^/  /'
  if [[ "${KILL_STALE}" == "1" ]]; then
    echo "KILL_STALE=1 set — reaping..."
    # shellcheck disable=SC2086
    kill ${STALE} 2>/dev/null || true
    sleep 1
    LEFT="$(stale_pf_pids)"
    if [[ -n "${LEFT}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${LEFT} 2>/dev/null || true
    fi
  else
    echo
    echo "Re-run with KILL_STALE=1 ./scripts/port-forward.sh to auto-reap them," >&2
    echo "or kill them by hand:  kill ${STALE//$'\n'/ }" >&2
    exit 1
  fi
fi

# --- pre-flight: every target port must be free -------------------------------
port_holder() {
  # Prints "<command> (PID <pid>)" for the first listener on $1, else nothing.
  # The trailing `|| true` keeps `set -e` + `pipefail` from aborting the script
  # when lsof has nothing to report (the "happy path" of an unoccupied port).
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -F pcn 2>/dev/null \
    | awk '/^p/{pid=substr($0,2)} /^c/{cmd=substr($0,2); printf "%s (PID %s)\n", cmd, pid; exit}' \
    || true
}

BLOCKED=0
for spec in "vectorizer ${VECTORIZER_PORT}" "question-api ${QA_PORT}" "${POSTGRES_SVC} ${POSTGRES_PORT}" "${REDIS_SVC} ${REDIS_PORT}"; do
  read -r label port <<<"${spec}"
  holder="$(port_holder "${port}")"
  if [[ -n "${holder}" ]]; then
    echo "ERROR: port ${port} (for ${label}) is held by ${holder}" >&2
    BLOCKED=1
  fi
done
if (( BLOCKED )); then
  echo >&2
  echo "Free the ports above (or override e.g. VECTORIZER_PORT=8011) and re-run." >&2
  exit 1
fi

if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "ERROR: namespace '${NAMESPACE}' does not exist (nothing to forward)." >&2
  exit 1
fi

# --- launch -------------------------------------------------------------------
echo "Forwarding (namespace=${NAMESPACE}):"
echo "  http://localhost:${VECTORIZER_PORT}     -> svc/vectorizer:8000"
echo "  http://localhost:${QA_PORT}             -> svc/question-api:8000"
echo "  postgresql://localhost:${POSTGRES_PORT} -> svc/${POSTGRES_SVC}:5432"
echo "  redis://localhost:${REDIS_PORT}         -> svc/${REDIS_SVC}:6379"
echo

kubectl -n "${NAMESPACE}" port-forward "svc/vectorizer"      "${VECTORIZER_PORT}:8000" &
PF_PIDS+=("$!")
kubectl -n "${NAMESPACE}" port-forward "svc/question-api"    "${QA_PORT}:8000" &
PF_PIDS+=("$!")
kubectl -n "${NAMESPACE}" port-forward "svc/${POSTGRES_SVC}" "${POSTGRES_PORT}:5432" &
PF_PIDS+=("$!")
kubectl -n "${NAMESPACE}" port-forward "svc/${REDIS_SVC}"    "${REDIS_PORT}:6379" &
PF_PIDS+=("$!")

wait
