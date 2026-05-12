# rag-evals

DeepEval-based retriever benchmark for the `rag-pgvector` workspace. The benchmark drives the shared `VectorStorePort`, wraps retrieved chunks as DeepEval `LLMTestCase` retrieval context, and sweeps `top_k` plus cosine-distance threshold values against a hand-curated golden set for `BILLS-115hr1625enr`.

## Configuration

| Key | Default | Purpose |
|---|---|---|
| `DEEPEVAL_JUDGE_PROVIDER` | `anthropic` | Judge backend: `anthropic` or `ollama`. |
| `DEEPEVAL_TOP_K_GRID` | `3,5,8` | Comma-separated top-k values to sweep. |
| `DEEPEVAL_THRESHOLD_GRID` | `0.4,0.6,0.8` | Comma-separated cosine-distance thresholds. Lower is stricter. |
| `DEEPEVAL_GOLDENS_PATH` | `evals/src/rag_evals/data/goldens_bills_115hr1625enr.json` | Golden dataset path. |
| `PACKAGE_ID` | `BILLS-115hr1625enr` | Optional CLI override applied to each golden metadata filter. |

The live benchmark also needs the same retrieval dependencies as `question-api`: `DATABASE_URL`, Bedrock embedding credentials, and either `ANTHROPIC_API_KEY` or a reachable Ollama service depending on the judge provider.

## Run

```bash
./scripts/eval-retrieval.sh
```

Override sweep values per run:

```bash
TOP_K_GRID=3,6,8 THRESHOLD_GRID=0.4,0.6,0.8 ./scripts/eval-retrieval.sh
```

The CLI prints a markdown table with precision, recall, and relevancy for each grid cell plus the best setting for each metric.

## Tests

```bash
uv run pytest -q
uv run pytest -m integration evals/tests/
```

The default test tier uses fake ports and stub metrics, so it does not call a database, Bedrock, Anthropic, or Ollama. The integration test skips unless credentials, a reachable pgvector database, and ingested `BILLS-115hr1625enr` rows are present.
