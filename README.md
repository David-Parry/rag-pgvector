# rag-pgvector

A **pip**-managed Python 3.12 monorepo for a small, opinionated RAG stack:

- `vectorizer/` — FastAPI pod that pulls PDFs from [api.govinfo.gov](https://api.govinfo.gov), extracts text with PyMuPDF, splits with LangChain, embeds with an approved AWS Bedrock embedding model, and upserts into a vanilla `postgres:17 + apt postgresql-17-pgvector` database.
- `question-api/` — FastAPI pod that answers strictly-grounded questions: it embeds the incoming question, retrieves top-k chunks from pgvector with a metadata filter and similarity threshold, then asks direct Anthropic Claude to answer using only that context. Each request carries a client `sessionId` (UUID); LangGraph checkpoints per-thread state in the Helm-installed Redis Stack service (messages plus per-turn ACA snapshots).
- `evals/` — DeepEval retriever benchmark that sweeps pgvector `top_k` and cosine-distance thresholds against hand-curated goldens for `BILLS-115hr1625enr`.
- `libs/rag-core/` — shared `Protocol` ports, the grounded system prompt, the chunk splitter, settings, and structlog config (DRY for both apps without coupling their deployments).
- `infra/` — custom `postgres-pgvector` Dockerfile and an umbrella Helm chart that deploys all three pods (`postgres`, `vectorizer`, `question-api`) into Docker Desktop's built-in Kubernetes.

## Architecture

```mermaid
flowchart LR
    subgraph Laptop["Laptop (Docker Desktop host)"]
        User[curl / client]
    end

    User -->|"POST localhost:8001/ingest"| PFv[kubectl port-forward 8001 -> svc/vectorizer:8000]
    User -->|"POST localhost:8002/ask"| PFq[kubectl port-forward 8002 -> svc/question-api:8000]

    subgraph Cluster["Helm release: rag-pgvector"]
        PFv --> Vec[vectorizer Pod]
        PFq --> QA[question-api Pod]
        Vec -->|UPSERT chunks| PG[("postgres:17 + pgvector Pod")]
        QA -->|cosine search top-k| PG
    end

    Vec -->|HTTPS| Gov[api.govinfo.gov/packages]
    Vec -->|Titan v2 Embed| Bedrock[(AWS Bedrock)]
    QA -->|Titan v2 Embed| Bedrock
    QA -->|Grounded prompt| Anthropic[Direct Anthropic Claude API]
```

## Service flows

The two pods are independently deployable microservices. The vectorizer is the write side (ingest + embed + upsert); the question-api is the read side (embed + retrieve + ground + generate). They share nothing at runtime — only the pgvector table and the `Protocol` ports in `libs/rag-core`.

### Vectorizer — `POST /ingest` → pgvector

```mermaid
flowchart TD
    Client["curl / client"] -->|"POST /ingest IngestRequest"| Route["FastAPI route<br/>vectorizer/api/routes.py"]
    Route --> Svc["VectorizeService.ingest<br/>vectorizer/domain/vectorize_service.py"]

    Svc -->|"list_packages collection, dates, pageSize"| Gov["GovInfoClient<br/>vectorizer/adapters/govinfo_client.py"]
    Gov -->|"HTTPS GET /collections/{c}"| GovApi[("api.govinfo.gov")]
    GovApi -->|"packages[] + nextPage"| Gov
    Gov -->|"async yield package summaries"| Svc

    Svc -->|"per packageId<br/>download_pdf"| Gov
    Gov -->|"GET /packages/{id}/summary + /pdf"| GovApi
    GovApi -->|"PDF bytes + title metadata"| Gov
    Gov -->|"PdfDocument bytes, title, sourceUrl"| Svc

    Svc -->|"loader.load PdfDocument"| Pdf["PyMuPdfLoader<br/>vectorizer/adapters/pdf_loader.py"]
    Pdf -->|"fitz.open stream<br/>page.get_text"| Pdf
    Pdf -->|"one Chunk per non-empty page<br/>pageNumber, totalPages"| Svc

    Svc -->|"splitter.split_text per page"| Split["chonkie RecursiveChunker<br/>rag_core.chunking<br/>legislative rules, chunk_size=1600"]
    Split -->|"text splits"| Svc

    Svc -->|"build Chunk with<br/>uuidv5 packageId|page|chunkIndex<br/>+ enriched metadata"| Svc

    Svc -->|"store.add_chunks chunks"| Store["PgVectorStoreAdapter<br/>vectorizer/adapters/pgvector_store.py"]
    Store -->|"aadd_documents docs, ids"| Lc["langchain_postgres<br/>PGVectorStore"]
    Lc -->|"embed_documents texts"| Titan["TitanEmbeddingsAdapter<br/>vectorizer/adapters/titan_embeddings.py"]
    Titan -->|"Bedrock InvokeModel<br/>amazon.titan-embed-text-v2:0 1024-dim"| Bedrock[("AWS Bedrock")]
    Bedrock -->|"vectors"| Titan
    Titan -->|"list of 1024-dim vectors"| Lc
    Lc -->|"UPSERT id, content, metadata, embedding"| PG[("postgres:17 + pgvector<br/>table = DATABASE_COLLECTION")]

    PG -->|"rows written"| Store
    Store -->|"written count"| Svc
    Svc -->|"IngestResponse<br/>ingested, packages, skipped"| Route
    Route -->|"200 OK JSON"| Client
```

Notes:

- `VectorizeService` is pure orchestration — every IO call goes through a port adapter (`GovInfoClientPort`, `DocumentLoaderPort`, `VectorStorePort`).
- Chunk IDs are deterministic UUIDv5 of `packageId|pageNumber|chunkIndex` under a fixed namespace, so re-ingesting the same package upserts in place (the `id` column in pgvector is typed `UUID`, so the id has to be a real UUID — not a hex digest).
- Embedding is *not* called directly by `VectorizeService`; `PGVectorStore` calls `TitanEmbeddingsAdapter.embed_documents` internally during `aadd_documents`.

### Question-API — `POST /ask` → grounded answer

```mermaid
flowchart TD
    Client["curl / client"] -->|"POST /ask AskRequest<br/>question, sessionId, metadata, topK, threshold"| Route["FastAPI route<br/>question_api/api/routes.py"]
    Route --> Svc["AskService + LangGraph<br/>question_api/domain/ask_service.py<br/>ask_graph.py"]

    Svc -->|"config.thread_id = sessionId<br/>Redis checkpointer"| Redis[("Redis Stack<br/>langgraph-checkpoint-redis")]
    Svc -->|"store.similarity_search<br/>question, k, metadata_filter"| Retr["PgVectorRetrieverAdapter<br/>question_api/adapters/pgvector_retriever.py"]
    Retr -->|"asimilarity_search_with_score"| Lc["langchain_postgres<br/>PGVectorStore"]

    Lc -->|"embed_query question"| Titan["TitanEmbeddingsAdapter<br/>question_api/adapters/titan_embeddings.py"]
    Titan -->|"Bedrock InvokeModel<br/>titan-embed-text-v2:0"| Bedrock[("AWS Bedrock")]
    Bedrock -->|"1024-dim query vector"| Titan
    Titan -->|"query vector"| Lc

    Lc -->|"SELECT ... ORDER BY embedding &lt;=&gt; q<br/>LIMIT k WHERE metadata @&gt; filter"| PG[("postgres:17 + pgvector")]
    PG -->|"top-k rows + cosine distance"| Lc
    Lc -->|"Document + score pairs"| Retr
    Retr -->|"list of RetrievedChunk<br/>id, text, metadata, score"| Svc

    Svc -->|"keep score &lt;= threshold<br/>cosine distance: lower = closer"| Filter{"any kept?"}
    Filter -- "no" --> Empty["AskResponse<br/>'I don't know based on the provided context.'<br/>citations=[], used_context_count=0"]
    Empty --> Route

    Filter -- "yes" --> Build["build_user_prompt<br/>rag_core/prompts.py<br/>numbered CONTEXT block:<br/>[i] packageId, sourceUrl, page + chunk text"]
    Build -->|"SYSTEM_PROMPT_QA + user prompt"| LLM["LLMPort.generate<br/>system, user"]

    LLM -->|generate| Anthropic["AnthropicLLMAdapter<br/>Messages API"]
    Anthropic --> Ans["grounded answer text"]

    Ans --> ToCit["chunks_to_citations + aca_truth_turns<br/>(per-turn ACA snapshot)"]
    ToCit --> Resp["AskResponse<br/>answer, citations[],<br/>usedContextCount, provider"]
    Resp --> Route
    Route -->|"200 OK JSON"| Client
```

Notes:

- The question is embedded by `TitanEmbeddingsAdapter.embed_query` *inside* `PGVectorStore.asimilarity_search_with_score` — `AskService` never touches embeddings directly.
- pgvector returns cosine **distance**, so `filter_chunks_by_threshold` in `question_api/domain/ask_retrieval.py` (same rule as the former `AskService._apply_threshold`) keeps chunks with `score <= threshold` (lower = more similar).
- Each `POST /ask` requires `sessionId` (UUID), used as LangGraph `thread_id`. Session checkpoints live in Redis Stack (`LANGGRAPH_REDIS_URL`, defaulted by Helm to `redis://rag-redis-stack:6379`) with TTL from `SESSION_CHECKPOINT_TTL_DAYS` (default 5 days, `SESSION_CHECKPOINT_TTL_REFRESH_ON_READ`). State channels include `messages` and per-turn `aca_truth_turns` keyed to message ids.
- If nothing survives the threshold, the service short-circuits with the fixed `"I don't know based on the provided context."` reply and never calls the LLM (no spend, no hallucination surface).
- Grounding happens in `rag_core.prompts.build_user_prompt`: kept chunks become a numbered `CONTEXT:` block carrying `packageId`, `sourceUrl`, and `pageNumber`, paired with `SYSTEM_PROMPT_QA` which forbids tool use and mandates a trailing `Sources:` section.
- The LLM is a `Protocol` port implemented by direct Anthropic Claude API calls in `question_api/core/composition.py`.

## Prerequisites

- **Windows**, macOS, or Linux with [Docker Desktop](https://www.docker.com/products/docker-desktop/), with **Kubernetes enabled**: `Docker Desktop → Settings → Kubernetes → Enable Kubernetes → Apply & restart`. The cluster appears in `kubectl config get-contexts` as `docker-desktop`.
- **Python** 3.12 and **pip** (create a repo-local venv: `python -m venv .venv`, then `pip install -r requirements/requirements-dev.txt`). Optional: [pip-tools](https://pip-tools.readthedocs.io/) (`pip-compile`) to refresh pinned requirement files from the `requirements/*.in` inputs. See [documentation/PYTHON_PIP_WORKFLOW.md](documentation/PYTHON_PIP_WORKFLOW.md).
- `helm` ≥ 3.13 (macOS/Linux: `brew install helm`; Windows: `winget install Helm.Helm` or [Helm install docs](https://helm.sh/docs/intro/install/))
- `kubectl` (macOS/Linux: `brew install kubectl`; Windows: `winget install Kubernetes.kubectl` or use kubectl bundled with Docker Desktop)

> Docker Desktop's built-in Kubernetes shares the Docker daemon's image store, so locally-built images are visible to the cluster without any push or `kind load` step. We do not use kind, minikube, or any external cluster tool.

## Environment variables

Copy and edit `.env`:

```bash
cp .env.example .env
$EDITOR .env
```

| Key | What it is | Required when |
|-----|-----------|---------------|
| `ANTHROPIC_API_KEY_FILE` / `ANTHROPIC_API_KEY` | Direct Anthropic API key file or value for Claude generation | always |
| `ANTHROPIC_DIRECT_MODEL` | Direct Anthropic model name, e.g. `claude-3-5-sonnet-latest` | optional |
| `AWS_REGION` | Region used for embedding AWS clients | always |
| `EMBEDDING_MODEL` | Embedding model ID for the direct embedding Bedrock credential path | always |
| `BEDROCK_EMBEDDING_DIMENSIONS` | `1024` | always |
| `AWS_PROFILE` / `AWS_DEFAULT_PROFILE` | Optional local AWS profile that Helm can export into temporary pod credentials for embeddings | local Docker Desktop with `aws.auth.mode=accessKey` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | Optional local AWS credentials for embeddings | only if `aws.auth.mode=accessKey` |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key for the embedding account; embeddings use this old direct credential path | embeddings |
| `RAG_INTERNAL_NETWORK` / `RAG_ON_PREM` | Set to `1` only for internal/on-prem installs that intentionally do not inject Bedrock embedding credentials | internal/on-prem only |
| `GOVINFO_API_KEY` | Free key from <https://api.data.gov/signup/> | always |
| `DATABASE_URL` | psycopg3 URL for pgvector | always |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_SCORE_THRESHOLD` | Defaults `5` / `0.25` | optional |
| `DEEPEVAL_JUDGE_PROVIDER` | `anthropic` or `ollama` for the retriever benchmark judge | benchmark runs |
| `DEEPEVAL_TOP_K_GRID` / `DEEPEVAL_THRESHOLD_GRID` | Comma-separated retriever benchmark sweep grids | optional |
| `DEEPEVAL_GOLDENS_PATH` | Golden dataset path for `rag-evals` | optional |

## Authentication

Direct Anthropic Claude is the question-answering path. Put the API key in `claudeapi.txt` and set `ANTHROPIC_API_KEY_FILE=claudeapi.txt`, or set `ANTHROPIC_API_KEY` directly in the environment. `claudeapi.txt` is ignored by Git.

Embeddings use the existing Bedrock embedding path: `EMBEDDING_MODEL`, `BEDROCK_EMBEDDING_DIMENSIONS`, and `AWS_BEARER_TOKEN_BEDROCK` (or direct AWS keys if that is how the embedding account is configured). Anthropic does not provide embeddings, so changing this requires selecting a replacement embedding provider.

For local Helm deployments, `scripts/helm-install.sh` and `scripts/ps/Helm-Install.ps1` auto-select embedding auth. They use a real `AWS_BEARER_TOKEN_BEDROCK` when present, otherwise AWS keys/profile credentials when available. Outside the internal/on-prem network, missing embedding credentials fail fast instead of deploying an `/ask` endpoint that cannot embed questions. For internal/on-prem installs that intentionally provide embeddings another way, set `RAG_INTERNAL_NETWORK=1` (or `RAG_ON_PREM=1`) to allow `aws.auth.mode=none`. For EKS, use `aws.auth.mode=irsa` and set `aws.auth.irsaRoleArn` to the embedding role.

## Local pod workflow (default)

### Bash (macOS / Linux / WSL)

```bash
# 1. Verify Docker Desktop Kubernetes is enabled and build the three images
bash scripts/docker-desktop-up.sh

# 2. Install the Helm release (reads .env)
bash scripts/helm-install.sh

# 3. Forward all three services to the laptop
bash scripts/port-forward.sh
```

### Windows (PowerShell, Docker Desktop Kubernetes)

Use the scripts under `scripts\ps\` (or the dispatcher `.\Rag.ps1`). **Order matters:** build images and load them into the cluster **before** Helm installs the release, so pods start with local `rag-pgvector/*:0.1.0` images that already exist on the Docker daemon / cluster.

| Step | What to run | Purpose |
|------|-------------|---------|
| 0 | Copy `.env.example` to `.env` and fill keys (Anthropic, Bedrock embedding, GovInfo, `DATABASE_URL`, Redis URL for LangGraph, etc.) | Helm and apps read credentials from `.env` |
| 1a | **If** Docker builds can reach public PyPI: `cd scripts\ps` then `.\Rag.ps1 docker-desktop-up` (or `.\Docker-Desktop-Up.ps1`) | Build `postgres`, `vectorizer`, `question-api` images and import them into Docker Desktop Kubernetes |
| 1b | **If** your network requires an internal PyPI mirror (e.g. JFrog Artifactory): `.\scripts\ps\env_var_artifactory.ps1` **instead of** step 1a | Resolves the package index (from `pip.ini` as `RAG_DOCKER_PIP_CONFIG_FILE`, one-line `RAG_PIP_INDEX_URL_FILE` / legacy `RAG_UV_DEFAULT_INDEX_FILE`, `RAG_DOCKER_PIP_INDEX_URL` / legacy `RAG_DOCKER_UV_DEFAULT_INDEX`) and **runs `Docker-Desktop-Up.ps1` for you**. Do not run both 1a and 1b for the same build. |
| 2 | `.\Rag.ps1 helm-install` (or `.\Helm-Install.ps1`) | `helm upgrade --install` the chart; loads repo `.env` |
| 3 | `$env:KILL_STALE = '1'; .\Rag.ps1 port-forward` if stale kubectl forwards hold ports; otherwise `.\Rag.ps1 port-forward` | `kubectl port-forward` for vectorizer, question-api, postgres |

**Flow you should *not* use:** Helm install **before** Docker Desktop Up when you depend on **locally built** images. The chart uses tags such as `rag-pgvector/question-api:0.1.0`; those images must exist after `docker-desktop-up` (or `env_var_artifactory.ps1`) before Helm can schedule healthy pods.

**Restart `question-api` only (after code or image changes):** from `scripts\ps`, run `.\Rag.ps1 restart-question-api` (or `.\Restart-QuestionApi.ps1`). That performs `kubectl rollout restart` on the Deployment labeled `app.kubernetes.io/component=question-api` in namespace `rag` (override with `$env:NAMESPACE`). Rebuild images with `.\Rag.ps1 docker-desktop-up` when you need new application code inside the cluster.

Then use Git Bash or WSL with `scripts/ask.sh`, or native Windows `scripts\ps\Ask.ps1`, or curl against `http://localhost:8001` / `http://localhost:8002` as in the examples below.

```bash
# Vectorize a govinfo collection (small sample)
curl -X POST http://localhost:8001/ingest \
  -H 'content-type: application/json' \
  -d '{"collection":"BILLS","lastModifiedStartDate":"2026-01-01T00:00:00Z","pageSize":25,"maxPackages":5}'

# Ask a grounded question
curl -X POST http://localhost:8002/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What does the latest BILLS package say about appropriations?","metadata":{"collection":"BILLS"},"topK":5}'
```

## Running example (helper scripts)

Once Helm is installed and `bash scripts/port-forward.sh` is up (see [Local pod workflow](#local-pod-workflow-default)), the two helper scripts in `scripts/` cover the full ingest-then-ask demo without writing curl by hand.

### 1. Load a single govinfo PDF into pgvector

```bash
./scripts/ingest-package.sh BILLS-115hr1625enr
```

This wraps `POST http://localhost:8001/ingest/package`. The vectorizer pod resolves the packageId against `api.govinfo.gov/packages/{id}/summary` + `/pdf`, splits each page with the shared `chonkie.RecursiveChunker` configured with legislative rules (SEC., TITLE, §, etc. as level-0 boundaries; chunk_size=1600 chars), embeds every split with Titan v2 (1024-dim), and upserts into `rag_chunks` with a deterministic UUIDv5 chunk id (so re-running the same packageId is idempotent).

Expected response shape:

```json
{ "ingested": 3375, "packages": 1, "skipped": 0, "collection": "BILLS" }
```

Verify the rows actually landed in pgvector:

```bash
kubectl -n rag exec rag-postgres-0 -- psql -U rag -d rag -At \
  -c "select count(*), count(distinct metadata->>'packageId') as packages from rag_chunks;"
```

The `rag_chunks` table is created with renamed/extended columns (overrides on
`langchain-postgres`'s defaults):

| Column | Type | Source |
|---|---|---|
| `id` | `uuid` (PK) | deterministic UUIDv5 of `packageId\|pageNumber\|chunkIndex` |
| `content` | `text` | chunk text |
| `embedding` | `vector(1024)` | Titan v2 embedding |
| `metadata` | `jsonb` | full chunk metadata blob (packageId, pageNumber, sourceUrl, ...) |
| `embedding_model` | `text` | hoisted from metadata, e.g. `amazon.titan-embed-text-v2` |
| `embedding_model_version` | `text` | hoisted from metadata, e.g. `0` |

The last two are *hoisted metadata columns*: PGVectorStore writes them from
`Document.metadata[<name>]` into typed columns on insert AND keeps them in the
JSON blob, so you can index/filter on them cheaply (`WHERE
embedding_model_version = '0'`) without paying for JSON extraction. The values
are stamped per-chunk by `PgVectorStoreAdapter.add_chunks` from the configured
`EMBEDDING_MODEL` (split on the trailing `:<rev>` suffix), so every
row is self-describing about which model produced its vector — handy when
swapping embedders or running A/B corpora in the same table.

Script knobs (override via env or positional arg):

| Var | Default | Purpose |
|---|---|---|
| `$1` / `PACKAGE_ID` | (required) | govinfo packageId — e.g. `BILLS-115hr1625enr`, `FR-2018-04-12`, `CREC-2018-01-03` |
| `VECTORIZER_URL` | `http://localhost:8001` | Base URL of the port-forwarded vectorizer |
| `METADATA` | `{"source":"ingest-package.sh"}` | JSON merged into every chunk's metadata (handy for tagging ingest runs) |

### 2. Ask a grounded question

```bash
./scripts/ask.sh
```

With **no arguments**, this asks a built-in demo question that targets the bill loaded above:

> What conditions does the Consolidated Appropriations Act place on U.S. assistance to the West Bank and Gaza, and what restrictions apply to the Palestinian Authority?

That question hits SEC. 1004 + Sec. 7038–7040 of `BILLS-115hr1625enr`, which is a self-contained multi-page policy framework, so the LLM has plenty of grounded context to write a structured, citable answer. You'll get back a multi-section response plus 6 citations, each with `packageId`, `pageNumber`, `sourceUrl`, cosine-distance `score`, and a ~220-char snippet.

Other invocation patterns:

```bash
./scripts/ask.sh "your custom question here"                     # custom question
QUESTION="..." ./scripts/ask.sh                                  # via env var
TOP_K=10 SCORE_THRESHOLD=0.50 ./scripts/ask.sh "..."             # tighter retrieval
METADATA='{"packageId":"BILLS-115hr1625enr"}' ./scripts/ask.sh   # restrict to one bill
RAW=1 ./scripts/ask.sh ...                                       # raw JSON (pipe to jq)
```

Notes on the script-level retrieval defaults:

- `ask.sh` ships with `TOP_K=6` and `SCORE_THRESHOLD=0.80` baked in as defaults so the no-arg invocation actually returns context. Over real bill text, Titan v2 cosine distances typically land in the 0.4–0.7 range, so the pod's stricter `RETRIEVAL_SCORE_THRESHOLD=0.25` default suppresses real matches for natural-language questions. To fall back to the pod-level defaults, delete those two lines in `scripts/ask.sh` (or override per call: `TOP_K=5 SCORE_THRESHOLD=0.25 ./scripts/ask.sh ...`).
- `scoreThreshold` is cosine **distance** (lower = stricter / more similar), not similarity. A chunk with `score=0.42` is closer to the query than one with `score=0.71`.
- If no chunks clear the threshold, `AskService` short-circuits with `"I don't know based on the provided context."` and never calls the LLM, so a 0-citation reply costs no Bedrock or Ollama tokens.

## Local non-pod workflow (fast iteration)

```bash
# Just run the postgres+pgvector image via compose
docker compose up -d postgres

# Install all workspace packages into .venv (from repo root)
python -m venv .venv
.venv\Scripts\pip install -r requirements\requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements/requirements-dev.txt   # macOS/Linux

# Run each service directly on the host
.venv\Scripts\uvicorn.exe vectorizer.main:app    --reload --port 8001
.venv\Scripts\uvicorn.exe question_api.main:app  --reload --port 8002
```

If you are on a network that blocks or MITMs public PyPI, use an internal mirror (for example JFrog) for both host `pip install` and image builds. Image builds: `documentation/DOCKER_PYPI_MIRROR.md`.

## Host Aliases

Docker Desktop Kubernetes resolves `host.docker.internal` from inside pods automatically. If you ever switch to a cluster that does not, override the chart value:

```yaml
qa:
  hostAliases:
    - ip: "192.168.65.2"        # the laptop's host IP from inside the cluster
      hostnames: ["host.docker.internal"]
```

## Repo layout

```
rag-pgvector/
├── pyproject.toml              # ruff, mypy, pytest config (no uv workspace)
├── requirements/               # pip: docker + dev requirement lists (.in / .txt)
├── .env.example
├── docker-compose.yml          # postgres-only convenience for non-pod dev
├── vectorizer/                 # service:  ingest + embed + upsert
├── question-api/               # service: retrieve + ground + generate
├── libs/rag-core/              # shared Protocols, prompts, chunker, settings
├── infra/
│   ├── docker/postgres-pgvector/   # FROM postgres:17 + apt postgresql-17-pgvector
│   └── helm/rag-pgvector/          # umbrella chart (3 pods, no Ollama, no Ingress)
├── scripts/                    # docker-desktop-up, helm-install, port-forward, seed-ingest
└── tests/                      # repo-level tests (helm lint + helm template)
```

## Tests

```bash
.venv/Scripts/pytest -q              # Windows; or: .venv/bin/pytest -q
```

Optional: `pip install build` then `python -m build` in a member package directory produces an sdist/wheel using that package's `[build-system]` (setuptools).

The test suite covers:

- Prompt + chunker invariants in `libs/rag-core/tests/`.
- Vectorizer domain orchestration with fake ports (`FakeGovInfoClient`, `FakeLoader`, `FakeStore`).
- govinfo HTTP client with `respx` mocks.
- Question-api retrieval/threshold/grounding with fake ports.
- Retriever benchmark grid, threshold filtering, and metadata-filter forwarding with fake ports.
- Helm chart smoke tests: `helm lint` + `helm template` in supported `aws.auth.mode` configurations.

A separate `@pytest.mark.integration` marker is reserved for testcontainers-backed adapter tests against a real pgvector — these are opt-in (run with `pytest -m integration`).
Retriever benchmark integration: `.venv/Scripts/pytest -m integration evals/tests/` (requires `BILLS-115hr1625enr` ingested).

## Things explicitly out of scope

- No CronJob ingestion scheduler — ingestion is operator-driven via `POST /ingest` per the original design.
