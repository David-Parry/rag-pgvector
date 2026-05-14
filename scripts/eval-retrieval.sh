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
#   DEEPEVAL_REPORT_FILE_TYPE=html ./scripts/eval-retrieval.sh
#   DEEPEVAL_LOG_PATH=documentation/eval-reports/latest.log ./scripts/eval-retrieval.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
if [[ -n "${RAG_PYTHON:-}" ]]; then
    PYTHON="${RAG_PYTHON}"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi

export PACKAGE_ID="${PACKAGE_ID:-BILLS-115hr1625enr}"
export DEEPEVAL_TOP_K_GRID="${TOP_K_GRID:-${DEEPEVAL_TOP_K_GRID:-3,5,8}}"
export DEEPEVAL_THRESHOLD_GRID="${THRESHOLD_GRID:-${DEEPEVAL_THRESHOLD_GRID:-0.4,0.6,0.8}}"
export DEEPEVAL_REPORT_FILE_TYPE="${DEEPEVAL_REPORT_FILE_TYPE:-markdown}"
export LOG_LEVEL="${DEEPEVAL_LOG_LEVEL:-INFO}"
DEEPEVAL_REPORT_FILE_TYPE="${DEEPEVAL_REPORT_FILE_TYPE,,}"

case "$DEEPEVAL_REPORT_FILE_TYPE" in
    md) DEEPEVAL_REPORT_FILE_TYPE="markdown" ;;
esac
if [[ "$DEEPEVAL_REPORT_FILE_TYPE" != "markdown" && "$DEEPEVAL_REPORT_FILE_TYPE" != "html" ]]; then
    echo "ERROR: DEEPEVAL_REPORT_FILE_TYPE must be 'markdown' or 'html'." >&2
    exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    anthropic_key_file="${ANTHROPIC_API_KEY_FILE:-claudeapi.txt}"
    if [[ -f "$anthropic_key_file" ]]; then
        export ANTHROPIC_API_KEY
        ANTHROPIC_API_KEY="$(tr -d '\r\n' < "$anthropic_key_file")"
    fi
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL is required. Start the environment and set DATABASE_URL before running eval retrieval." >&2
    exit 1
fi

db_netloc="$("$PYTHON" -c 'import os, urllib.parse; url=os.environ["DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:", 1); print(urllib.parse.urlsplit(url).netloc)' 2>/dev/null || true)"
db_host="${db_netloc%@*}"
db_host="${db_host##*@}"
db_host="${db_host%%:*}"
db_port="${db_netloc##*:}"
if [[ "$db_port" == "$db_netloc" || -z "$db_port" ]]; then
    db_port="5432"
fi

echo "Checking existing pgvector database at ${db_host}:${db_port} ..." >&2
"$PYTHON" - "$db_host" "$db_port" <<'PY'
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
if [[ "$DEEPEVAL_REPORT_FILE_TYPE" == "html" ]]; then
    report_extension="html"
else
    report_extension="md"
fi
report_path="${DEEPEVAL_REPORT_PATH:-${report_dir}/deepeval-${safe_package_id}-${timestamp}.${report_extension}}"
default_log_path="${report_path%.*}.log"
log_path="${DEEPEVAL_LOG_PATH:-${default_log_path}}"

mkdir -p "$(dirname "$report_path")"
mkdir -p "$(dirname "$log_path")"
: > "$log_path"

if [[ "$DEEPEVAL_REPORT_FILE_TYPE" == "html" ]]; then
    package_html="$("$PYTHON" -c 'import html, os; print(html.escape(os.environ["PACKAGE_ID"]))')"
    top_k_html="$("$PYTHON" -c 'import html, os; print(html.escape(os.environ["DEEPEVAL_TOP_K_GRID"]))')"
    threshold_html="$("$PYTHON" -c 'import html, os; print(html.escape(os.environ["DEEPEVAL_THRESHOLD_GRID"]))')"
    log_path_html="$(LOG_PATH="$log_path" "$PYTHON" -c 'import html, os; print(html.escape(os.environ["LOG_PATH"]))')"
    {
        echo '<!doctype html>'
        echo '<html lang="en">'
        echo '<head>'
        echo '  <meta charset="utf-8">'
        echo '  <title>DeepEval Retriever Benchmark Report</title>'
        echo '  <style>body{font-family:Arial,sans-serif;line-height:1.5;margin:2rem;max-width:1100px}table{border-collapse:collapse;width:100%;margin-top:1rem}th,td{border:1px solid #d0d7de;padding:.45rem;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#f6f8fa}code{background:#f6f8fa;padding:.15rem .3rem;border-radius:4px}</style>'
        echo '</head>'
        echo '<body>'
        echo '<main>'
        echo '<h1>DeepEval Retriever Benchmark Report</h1>'
        echo '<ul>'
        echo "  <li>Generated: ${generated_at}</li>"
        echo "  <li>Package ID: <code>${package_html}</code></li>"
        echo "  <li>Top-k grid: <code>${top_k_html}</code></li>"
        echo "  <li>Threshold grid: <code>${threshold_html}</code></li>"
        echo "  <li>Progress log: <code>${log_path_html}</code></li>"
        echo '</ul>'
    } | tee "$report_path"
else
    {
        echo "# DeepEval Retriever Benchmark Report"
        echo
        echo "- Generated: ${generated_at}"
        echo "- Package ID: ${PACKAGE_ID}"
        echo "- Top-k grid: ${DEEPEVAL_TOP_K_GRID}"
        echo "- Threshold grid: ${DEEPEVAL_THRESHOLD_GRID}"
        echo "- Progress log: ${log_path}"
        echo
    } | tee "$report_path"
fi

if "$PYTHON" -m rag_evals.cli 2> >(tee "$log_path" >&2) | tee -a "$report_path"; then
    true
else
    exit_code=$?
    if [[ "$DEEPEVAL_REPORT_FILE_TYPE" == "html" ]]; then
        log_path_html="$(LOG_PATH="$log_path" "$PYTHON" -c 'import html, os; print(html.escape(os.environ["LOG_PATH"]))')"
        echo "<section><h2>Error</h2><p>The eval command failed. See the progress log for command output: <code>${log_path_html}</code></p></section>" | tee -a "$report_path" >&2
        {
            echo '</main>'
            echo '</body>'
            echo '</html>'
        } | tee -a "$report_path" >/dev/null
    else
        {
            echo
            echo "## Error"
            echo
            echo "The eval command failed. See the progress log for command output: ${log_path}"
        } | tee -a "$report_path" >&2
    fi
    exit "$exit_code"
fi

if [[ "$DEEPEVAL_REPORT_FILE_TYPE" == "html" ]]; then
    {
        echo '</main>'
        echo '</body>'
        echo '</html>'
    } | tee -a "$report_path" >/dev/null
fi

echo "DeepEval report written to ${report_path}" >&2
echo "DeepEval progress log written to ${log_path}" >&2
