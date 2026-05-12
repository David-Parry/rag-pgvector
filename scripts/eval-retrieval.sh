#!/usr/bin/env bash
#
# Run the DeepEval pgvector retriever benchmark over the demo bill corpus.
#
# Usage:
#   ./scripts/eval-retrieval.sh
#   PACKAGE_ID=BILLS-115hr1625enr TOP_K_GRID=3,6,8 THRESHOLD_GRID=0.4,0.6,0.8 ./scripts/eval-retrieval.sh
#
set -euo pipefail

export PACKAGE_ID="${PACKAGE_ID:-BILLS-115hr1625enr}"
export DEEPEVAL_TOP_K_GRID="${TOP_K_GRID:-${DEEPEVAL_TOP_K_GRID:-3,5,8}}"
export DEEPEVAL_THRESHOLD_GRID="${THRESHOLD_GRID:-${DEEPEVAL_THRESHOLD_GRID:-0.4,0.6,0.8}}"

uv run python -m rag_evals.cli
