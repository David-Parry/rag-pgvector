#!/usr/bin/env bash
# Sample ingestion against the port-forwarded vectorizer pod.
# Customize via env vars or args.
set -euo pipefail

VECTORIZER_URL="${VECTORIZER_URL:-http://localhost:8001}"
COLLECTION="${COLLECTION:-BILLS}"
START="${LAST_MODIFIED_START:-2026-01-01T00:00:00Z}"
END="${LAST_MODIFIED_END:-}"
PAGE_SIZE="${PAGE_SIZE:-25}"
MAX_PACKAGES="${MAX_PACKAGES:-5}"

read -r -d '' BODY <<EOF || true
{
  "collection": "${COLLECTION}",
  "lastModifiedStartDate": "${START}",
  $( [[ -n "$END" ]] && printf '"lastModifiedEndDate": "%s",\n  ' "$END" )"pageSize": ${PAGE_SIZE},
  "maxPackages": ${MAX_PACKAGES},
  "metadata": {"tag": "demo"}
}
EOF

echo "POST ${VECTORIZER_URL}/ingest"
echo "$BODY"
echo

curl -fsS -X POST "${VECTORIZER_URL}/ingest" \
  -H 'content-type: application/json' \
  -d "$BODY"
echo
