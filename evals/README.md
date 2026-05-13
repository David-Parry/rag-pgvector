# rag-evals

DeepEval-based retriever benchmark for the `rag-pgvector` workspace. The benchmark drives the shared `VectorStorePort`, wraps retrieved chunks as DeepEval `LLMTestCase` retrieval context, and sweeps `top_k` plus cosine-distance threshold values against a hand-curated golden set for `BILLS-115hr1625enr`.

## Configuration

| Key | Default | Purpose |
|---|---|---|
| `DEEPEVAL_JUDGE_PROVIDER` | `anthropic` | Judge backend: `anthropic` or `ollama`. |
| `DEEPEVAL_VERBOSE_MODE` | `false` | DeepEval metric display verbosity. Keep `false` for clean report runs. |
| `DEEPEVAL_REPORT_FILE_TYPE` | `html` | Report format: `html` or `markdown`. The runners use `.html` or `.md` extensions accordingly. |
| `DEEPEVAL_TOP_K_GRID` | `3,5,8` | Comma-separated top-k values to sweep. |
| `DEEPEVAL_THRESHOLD_GRID` | `0.4,0.6,0.8` | Comma-separated cosine-distance thresholds. Lower is stricter. |
| `DEEPEVAL_GOLDENS_PATH` | `evals/src/rag_evals/data/goldens_bills_115hr1625enr.json` | Golden dataset path. |
| `PACKAGE_ID` | `BILLS-115hr1625enr` | Optional CLI override applied to each golden metadata filter. |
| `DEEPEVAL_LOG_LEVEL` | `INFO` | Log level used by report runners. Set to `DEBUG` only for troubleshooting because SDK debug logs can include sensitive headers. |
| `DEEPEVAL_MIN_PRECISION` | `0.5` | Minimum precision required for a grid cell to pass. |
| `DEEPEVAL_MIN_RECALL` | `0.5` | Minimum recall required for a grid cell to pass. |
| `DEEPEVAL_MIN_RELEVANCY` | `0.5` | Minimum relevancy required for a grid cell to pass. |
| `DEEPEVAL_LOG_PATH` | unset | Optional path for progress logs and third-party SDK output. When unset, no companion `.log` file is created. |

The live benchmark also needs the same retrieval dependencies as `question-api`: `DATABASE_URL`, Bedrock embedding credentials, and either `ANTHROPIC_API_KEY` or a reachable Ollama service depending on the judge provider.

When `ANTHROPIC_API_KEY` is not set, the benchmark runners load it from `ANTHROPIC_API_KEY_FILE` or `claudeapi.txt`.

The benchmark expects the pgvector environment to be running already. The runners do not start, stop, tear down, delete, or reset the vector database; they only check that `DATABASE_URL` is reachable before running the benchmark.

## Run

```bash
./scripts/eval-retrieval.sh
```

PowerShell:

```powershell
.\scripts\ps\Eval-Retrieval.ps1
```

Generate a markdown report:

```powershell
.\scripts\ps\Eval-Retrieval.ps1 -ReportFileType markdown
```

Override sweep values per run:

```bash
TOP_K_GRID=3,6,8 THRESHOLD_GRID=0.4,0.6,0.8 ./scripts/eval-retrieval.sh
```

The script writes a previewable HTML summary by default with explicit `PASS` or `FAIL` status for each grid cell. A cell passes only when precision, recall, and relevancy all meet the configured `DEEPEVAL_MIN_*` gates. Progress logs and third-party SDK output stay in the terminal unless `DEEPEVAL_LOG_PATH` or the PowerShell `-LogPath` parameter is provided.

Override the report destination per run:

```bash
DEEPEVAL_REPORT_PATH=dist/latest.html ./scripts/eval-retrieval.sh
```

PowerShell also supports parameters:

```powershell
.\scripts\ps\Eval-Retrieval.ps1 -TopKGrid '3,6,8' -ThresholdGrid '0.4,0.6,0.8' -ReportPath 'dist/latest.html'
```

Create a companion progress log only when needed:

```powershell
.\scripts\ps\Eval-Retrieval.ps1 -LogPath 'dist/latest.log'
```

## Tests

```bash
uv run pytest -q
uv run pytest -m integration evals/tests/
```

The default test tier uses fake ports and stub metrics, so it does not call a database, Bedrock, Anthropic, or Ollama. The integration test skips unless credentials, a reachable pgvector database, and ingested `BILLS-115hr1625enr` rows are present.
