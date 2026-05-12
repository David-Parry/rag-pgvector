#!/usr/bin/env bash
#
# Ask the question-api pod a single question over the port-forwarded service.
#
# The pod runs the AskService pipeline:
#   embed(question) with Titan v2  ->  pgvector similarity search
#   ->  prompt-stuff top-K chunks  ->  Bedrock / Ollama (per LLM_PROVIDER)
#   ->  AskResponse{ answer, citations, usedContextCount, provider }.
#
# Usage:
#   ./scripts/ask.sh
#   ./scripts/ask.sh "your question here"
#   QUESTION="..." ./scripts/ask.sh
#   TOP_K=10 SCORE_THRESHOLD=0.30 ./scripts/ask.sh "..."
#   METADATA='{"packageId":"BILLS-115hr1625enr"}' ./scripts/ask.sh "..."
#   QUESTION_API_URL=http://localhost:8002 ./scripts/ask.sh "..."
#
# Env vars:
#   QUESTION_API_URL  Base URL for the question-api pod  (default: http://localhost:8002)
#   QUESTION          Question text                      (overridden by $1 if given)
#   METADATA          JSON metadata filter for retrieval (default: {})
#   TOP_K             Override RETRIEVAL_TOP_K           (optional, 1..50)
#   SCORE_THRESHOLD   Override RETRIEVAL_SCORE_THRESHOLD (optional, >= 0)
#   RAW=1             Skip pretty-printing and dump the raw JSON response
#
set -euo pipefail

QUESTION_API_URL="${QUESTION_API_URL:-http://localhost:8002}"

# Default demo question: hits SEC. 1004 + Sec. 7038-7040 of the FY2018
# Consolidated Appropriations Act (BILLS-115hr1625enr), which gives the LLM
# enough self-contained policy to write a multi-section grounded answer.
DEFAULT_QUESTION="What conditions does the Consolidated Appropriations Act place on U.S. assistance to the West Bank and Gaza, and what restrictions apply to the Palestinian Authority?"
QUESTION="${1:-${QUESTION:-${DEFAULT_QUESTION}}}"

METADATA="${METADATA:-{}}"

# Demo-friendly retrieval defaults so a no-arg `./scripts/ask.sh` actually
# returns context with Titan v2 over the bills corpus (cosine distances on
# real bill text tend to fall in 0.4-0.7). Override per-call via env vars,
# or remove these lines to fall back to the pod's RETRIEVAL_TOP_K /
# RETRIEVAL_SCORE_THRESHOLD env defaults.
TOP_K="${TOP_K:-6}"
SCORE_THRESHOLD="${SCORE_THRESHOLD:-0.80}"

if ! command -v jq >/dev/null 2>&1; then
  echo "this script requires 'jq' (brew install jq)" >&2
  exit 1
fi

# Build the request body with jq so question / metadata are safely escaped and
# the optional topK / scoreThreshold keys are only included when set.
BODY="$(jq -nc \
  --arg q "${QUESTION}" \
  --argjson md "${METADATA}" \
  --arg topk "${TOP_K}" \
  --arg score "${SCORE_THRESHOLD}" \
  '{question:$q, metadata:$md}
   + (if $topk  == "" then {} else {topK:        ($topk  | tonumber)} end)
   + (if $score == "" then {} else {scoreThreshold:($score | tonumber)} end)')"

echo "POST ${QUESTION_API_URL}/ask"
echo "${BODY}" | jq .
echo

RESPONSE="$(curl -fsS -X POST "${QUESTION_API_URL}/ask" \
  -H 'content-type: application/json' \
  -d "${BODY}")"

if [[ "${RAW:-0}" == "1" ]]; then
  echo "${RESPONSE}" | jq .
  exit 0
fi

# Pretty-print: answer block, then a compact citations table.
echo "${RESPONSE}" | jq -r '
  "=== answer (provider=" + .provider + ", usedContextCount=" + (.usedContextCount|tostring) + ") ===",
  "",
  .answer,
  "",
  "=== citations ===",
  (.citations
   | to_entries[]
   | "[" + ((.key + 1)|tostring) + "] "
       + (.value.packageId // "?")
       + (if .value.pageNumber != null then " p." + (.value.pageNumber|tostring) else "" end)
       + "  score=" + ((.value.score|tostring) | .[0:6])
       + "\n     " + (.value.sourceUrl // "")
       + "\n     " + (.value.snippet // "" | gsub("\\s+"; " ") | .[0:220])
  )'
