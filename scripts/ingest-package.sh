#!/usr/bin/env bash
#
# Vectorize a single govinfo PDF by packageId via the port-forwarded vectorizer pod.
#
# The vectorizer pod resolves the packageId against api.govinfo.gov:
#   GET /packages/{packageId}/summary   (title + provenance)
#   GET /packages/{packageId}/pdf       (PDF bytes; redirects to CDN)
# splits with the shared chonkie RecursiveChunker (legislative rules), embeds with Titan v2,
# and upserts into pgvector with deterministic chunk ids.
#
# Usage:
#   ./scripts/ingest-package.sh BILLS-115hr1625enr
#   ./scripts/ingest-package.sh FR-2018-04-12
#   PACKAGE_ID=CREC-2018-01-03 ./scripts/ingest-package.sh
#   METADATA='{"source":"manual","tag":"smoke"}' ./scripts/ingest-package.sh BILLS-115hr1625enr
#   VECTORIZER_URL=http://localhost:8001 ./scripts/ingest-package.sh BILLS-115hr1625enr
#
# Env vars:
#   VECTORIZER_URL  Base URL for the vectorizer pod  (default: http://localhost:8001)
#   PACKAGE_ID      govinfo packageId                (overridden by $1 if given)
#   METADATA        JSON object merged into chunk metadata  (default: {"source":"ingest-package.sh"})
set -euo pipefail

VECTORIZER_URL="${VECTORIZER_URL:-http://localhost:8001}"
PACKAGE_ID="${1:-${PACKAGE_ID:-}}"
METADATA="${METADATA:-{\"source\":\"ingest-package.sh\"}}"

if [[ -z "${PACKAGE_ID}" ]]; then
  echo "usage: $0 <packageId>     (e.g. BILLS-115hr1625enr)" >&2
  echo "       or set PACKAGE_ID env var" >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "this script requires 'jq' (brew install jq)" >&2
  exit 1
fi

BODY="$(jq -nc \
  --arg pid "${PACKAGE_ID}" \
  --argjson md "${METADATA}" \
  '{packageId:$pid, metadata:$md}')"

echo "POST ${VECTORIZER_URL}/ingest/package"
echo "${BODY}" | jq .
echo

curl -fsS -X POST "${VECTORIZER_URL}/ingest/package" \
  -H 'content-type: application/json' \
  -d "${BODY}" | jq .
