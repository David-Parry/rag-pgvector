#!/usr/bin/env bash
#
# Run the DeepEval pgvector retriever benchmark over the demo bill corpus.
# Expects the pgvector environment to be running already; this script does not
# start, stop, tear down, delete, or reset the vector database.
#
# Usage:
#   ./scripts/eval-retrieval.sh
#   PACKAGE_ID=BILLS-115hr1625enr TOP_K_GRID=3,6,8 THRESHOLD_GRID=0.4,0.6,0.8 ./scripts/eval-retrieval.sh
#   DEEPEVAL_REPORT_PATH=documentation/eval-reports/latest.md ./scripts/eval-retrieval.sh
#
set -euo pipefail

export PACKAGE_ID="${PACKAGE_ID:-BILLS-115hr1625enr}"
export DEEPEVAL_TOP_K_GRID="${TOP_K_GRID:-${DEEPEVAL_TOP_K_GRID:-3,5,8}}"
export DEEPEVAL_THRESHOLD_GRID="${THRESHOLD_GRID:-${DEEPEVAL_THRESHOLD_GRID:-0.4,0.6,0.8}}"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL is required. Start the environment and set DATABASE_URL before running eval retrieval." >&2
    exit 1
fi

db_netloc="$(uv run python -c 'import os, urllib.parse; url=os.environ["DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1); print(urllib.parse.urlsplit(url).netloc)' 2>/dev/null || true)"
db_host="${db_netloc%@*}"
db_host="${db_host##*@}"
db_host="${db_host%%:*}"
db_port="${db_netloc##*:}"
if [[ "$db_port" == "$db_netloc" || -z "$db_port" ]]; then
    db_port="5432"
fi

echo "Checking existing pgvector database at ${db_host}:${db_port} ..." >&2
uv run python - "$db_host" "$db_port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=3):
        pass
except OSError as exc:
    raise SystemExit(
        "ERROR: pgvector database is not reachable at "
        f"{host}:{port}. Start the environment and port-forward Postgres first, "
        "for example: ./scripts/port-forward.sh"
    ) from exc
PY

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
report_dir="${DEEPEVAL_REPORT_DIR:-documentation/eval-reports}"
safe_package_id="${PACKAGE_ID//[^A-Za-z0-9._-]/_}"
report_path="${DEEPEVAL_REPORT_PATH:-${report_dir}/deepeval-${safe_package_id}-${timestamp}.md}"

mkdir -p "$(dirname "$report_path")"

{
    echo "# DeepEval Retriever Benchmark Report"
    echo
    echo "- Generated: ${generated_at}"
    echo "- Package ID: ${PACKAGE_ID}"
    echo "- Top-k grid: ${DEEPEVAL_TOP_K_GRID}"
    echo "- Threshold grid: ${DEEPEVAL_THRESHOLD_GRID}"
    echo
    uv run python -m rag_evals.cli
} | tee "$report_path"

echo "DeepEval report written to ${report_path}" >&2
