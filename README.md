# rag-pgvector

A `uv`-managed Python 3.12 monorepo for a small, opinionated RAG stack:

- `vectorizer/` — FastAPI pod that pulls PDFs from [api.govinfo.gov](https://api.govinfo.gov), extracts text with PyMuPDF, splits with LangChain, embeds with **AWS Bedrock Titan Text Embeddings v2 (1024-dim)**, and upserts into a vanilla `postgres:17 + apt postgresql-17-pgvector` database.
- `question-api/` — FastAPI pod that answers strictly-grounded questions: it embeds the incoming question with Titan v2, retrieves top-k chunks from pgvector with a metadata filter and similarity threshold, then asks a switchable LLM (Anthropic Claude Sonnet 4.5 by default, or a host-resident Ollama on the Docker Desktop laptop) to answer using only that context.
- `libs/rag-core/` — shared `Protocol` ports, the grounded system prompt, the chunk splitter, settings, and structlog config (DRY for both apps without coupling their deployments).
- `infra/` — custom `postgres-pgvector` Dockerfile and an umbrella Helm chart that deploys all three pods (`postgres`, `vectorizer`, `question-api`) into Docker Desktop's built-in Kubernetes.

## Architecture

```mermaid
flowchart LR
    subgraph Laptop["Laptop (Docker Desktop host)"]
        User[curl / client]
        HostOllama["Ollama (host process, :11434)"]
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
    QA -->|Grounded prompt| LLM{LLM_PROVIDER}
    LLM -->|anthropic| Anthropic[Anthropic Claude Sonnet 4.5]
    LLM -->|"ollama via host.docker.internal:11434"| HostOllama
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
    Client["curl / client"] -->|"POST /ask AskRequest<br/>question, metadata, topK, threshold"| Route["FastAPI route<br/>question_api/api/routes.py"]
    Route --> Svc["AskService.ask<br/>question_api/domain/ask_service.py"]

    Svc -->|"resolve top_k + threshold<br/>request > RetrievalSettings"| Svc
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

    LLM -->|"LLM_PROVIDER=anthropic"| Anthropic["AnthropicLLMAdapter<br/>ChatAnthropic claude-sonnet-4-5"]
    LLM -->|"LLM_PROVIDER=ollama"| Ollama["OllamaLLMAdapter<br/>host.docker.internal:11434"]
    Anthropic --> Ans["grounded answer text"]
    Ollama --> Ans

    Ans --> ToCit["_to_citations kept chunks<br/>packageId, sourceUrl, pageNumber,<br/>score, 280-char snippet"]
    ToCit --> Resp["AskResponse<br/>answer, citations[],<br/>used_context_count, provider"]
    Resp --> Route
    Route -->|"200 OK JSON"| Client
```

Notes:

- The question is embedded by `TitanEmbeddingsAdapter.embed_query` *inside* `PGVectorStore.asimilarity_search_with_score` — `AskService` never touches embeddings directly.
- pgvector returns cosine **distance**, so `AskService._apply_threshold` keeps chunks with `score <= threshold` (lower = more similar).
- If nothing survives the threshold, the service short-circuits with the fixed `"I don't know based on the provided context."` reply and never calls the LLM (no spend, no hallucination surface).
- Grounding happens in `rag_core.prompts.build_user_prompt`: kept chunks become a numbered `CONTEXT:` block carrying `packageId`, `sourceUrl`, and `pageNumber`, paired with `SYSTEM_PROMPT_QA` which forbids tool use and mandates a trailing `Sources:` section.
- The LLM is a `Protocol` port — swapping Anthropic for Ollama is a single `LLM_PROVIDER` env flip wired in `question_api/core/composition.py`.

## Prerequisites

- macOS or Linux with [Docker Desktop](https://www.docker.com/products/docker-desktop/), with **Kubernetes enabled**: `Docker Desktop → Settings → Kubernetes → Enable Kubernetes → Apply & restart`. The cluster appears in `kubectl config get-contexts` as `docker-desktop`.
- `uv` ≥ 0.5 (`brew install uv`)
- `helm` ≥ 3.13 (`brew install helm`)
- `kubectl` (`brew install kubectl`)
- (Optional) [`ollama`](https://ollama.com/) installed natively on the laptop if you want to use `LLM_PROVIDER=ollama`.

> Docker Desktop's built-in Kubernetes shares the Docker daemon's image store, so locally-built images are visible to the cluster without any push or `kind load` step. We do not use kind, minikube, or any external cluster tool.

## Environment variables

Copy and edit `.env`:

```bash
cp .env.example .env
$EDITOR .env
```

| Key | What it is | Required when |
|-----|-----------|---------------|
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key (single bearer token) | `aws.auth.mode=bearer` (default) |
| `AWS_REGION` | Region the Bedrock key was generated in | always |
| `BEDROCK_EMBEDDING_MODEL_ID` | `amazon.titan-embed-text-v2:0` | always |
| `BEDROCK_EMBEDDING_DIMENSIONS` | `1024` | always |
| `ANTHROPIC_API_KEY` | Anthropic key for Claude Sonnet 4.5 | when `LLM_PROVIDER=anthropic` (default) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | always |
| `LLM_PROVIDER` | `anthropic` (default) or `ollama` | always |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | when `LLM_PROVIDER=ollama` |
| `OLLAMA_MODEL` | e.g. `llama3.1:8b` | when `LLM_PROVIDER=ollama` |
| `GOVINFO_API_KEY` | Free key from <https://api.data.gov/signup/> | always |
| `DATABASE_URL` | psycopg3 URL for pgvector | always |
| `RETRIEVAL_TOP_K` / `RETRIEVAL_SCORE_THRESHOLD` | Defaults `5` / `0.25` | optional |

## AWS Bedrock authentication

Two modes are wired end-to-end through both the Python settings layer and the Helm chart's `aws.auth.mode`:

1. **Bearer token (default)** — generate a long-term Bedrock API key in the AWS console (`Amazon Bedrock → API keys → Generate long-term API key`) with a minimum-permission policy, e.g.:

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        { "Effect": "Allow",
          "Action": ["bedrock:InvokeModel"],
          "Resource": ["arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"] }
      ]
    }
    ```

   Make sure `amazon.titan-embed-text-v2:0` is enabled under `Bedrock → Model access`. Put the key in `AWS_BEARER_TOKEN_BEDROCK`. `langchain-aws` (>=0.2.28) reads this env var automatically — no boto3 session is needed.

2. **IRSA** (real EKS only) — pass `--set aws.auth.mode=irsa --set aws.auth.irsaRoleArn=arn:aws:iam::...:role/...`. The chart annotates the ServiceAccount with `eks.amazonaws.com/role-arn` and renders no AWS keys into the Secret.

Bedrock API keys are **region-locked**. The bearer-token path also pollutes the process env at startup (a known `langchain-aws` quirk, harmless for our single-tenant pods).

## Local pod workflow (default)

```bash
# 1. Verify Docker Desktop Kubernetes is enabled and build the three images
bash scripts/docker-desktop-up.sh

# 2. Install the Helm release (reads .env)
bash scripts/helm-install.sh

# 3. Forward all three services to the laptop
bash scripts/port-forward.sh
```

Then:

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
`BEDROCK_EMBEDDING_MODEL_ID` (split on the trailing `:<rev>` suffix), so every
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
- If no chunks clear the threshold, `AskService` short-circuits with `"I don't know based on the provided context."` and never calls the LLM — so a 0-citation reply costs no Anthropic / Ollama tokens.

## Local non-pod workflow (fast iteration)

```bash
# Just run the postgres+pgvector image via compose
docker compose up -d postgres

# Sync the workspace
uv sync --all-packages

# Run each service directly on the host
uv run uvicorn vectorizer.main:app    --reload --port 8001
uv run uvicorn question_api.main:app  --reload --port 8002
```

## Using Ollama (on the host, not in the cluster)

The chart **does not deploy Ollama**. Instead, it expects Ollama to run on the Docker Desktop host (your laptop):

```bash
ollama serve &              # if not already running
ollama pull llama3.1:8b
curl http://localhost:11434/api/tags  # sanity check
```

Then re-deploy with `LLM_PROVIDER=ollama` in your `.env` and re-run `bash scripts/helm-install.sh`. The question-api pod calls `http://host.docker.internal:11434` from inside the cluster.

Docker Desktop Kubernetes resolves `host.docker.internal` from inside pods automatically. If you ever switch to a cluster that doesn't (e.g. a remote cluster), override the chart value:

```yaml
qa:
  hostAliases:
    - ip: "192.168.65.2"        # the laptop's host IP from inside the cluster
      hostnames: ["host.docker.internal"]
```

## Repo layout

```
rag-pgvector/
├── pyproject.toml              # uv workspace root
├── uv.lock
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
uv run pytest -q              # 19 tests, no network/services required
```

The test suite covers:

- Prompt + chunker invariants in `libs/rag-core/tests/`.
- Vectorizer domain orchestration with fake ports (`FakeGovInfoClient`, `FakeLoader`, `FakeStore`).
- govinfo HTTP client with `respx` mocks.
- Question-api retrieval/threshold/grounding with fake ports.
- Helm chart smoke tests: `helm lint` + `helm template` in all three `aws.auth.mode`s and both LLM providers.

A separate `@pytest.mark.integration` marker is reserved for testcontainers-backed adapter tests against a real pgvector — these are opt-in (run with `pytest -m integration`).

## Things explicitly out of scope

- No CronJob ingestion scheduler — ingestion is operator-driven via `POST /ingest` per the original design.
- No in-cluster Ollama; the host-resident model is used when `LLM_PROVIDER=ollama`.
