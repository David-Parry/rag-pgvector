#!/usr/bin/env bash
# Install/upgrade the helm release WITHOUT question-api, then start port-forwards
# for postgres, redis-stack, and vectorizer so question-api can run from the IDE
# (PyCharm) against in-cluster dependencies on localhost.
#
# Leaves port 8000 free for the IDE-run question-api.
#
# Env overrides are forwarded to the underlying scripts; see their headers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export QA_LOCAL=1

echo "==> helm install (QA_LOCAL=1, question-api disabled in cluster)"
bash "${SCRIPT_DIR}/helm-install.sh" "$@"

echo
echo "==> port-forward (skipping svc/question-api)"
echo "    Start question-api in PyCharm against localhost:5432 (postgres) and"
echo "    localhost:6379 (redis). It will listen on http://localhost:8000."
echo
exec bash "${SCRIPT_DIR}/port-forward.sh"
