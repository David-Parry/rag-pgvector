# question-api

Project 2 of the rag-pgvector monorepo. A FastAPI pod that answers strictly-grounded questions over the data loaded by `vectorizer`.

## Endpoints

- `POST /ask` — body: `{ "question": "...", "metadata": {...}, "topK": 5 }`. Returns `{ "answer": "...", "citations": [...], "usedContextCount": n }`.
- `GET /healthz` — readiness probe.

## LLM provider

Selected via `LLM_PROVIDER`:

- `bedrock` (default) — uses `BEDROCK_CONNECTION_SECRET_NAME` and `BEDROCK_ROLE_ARN` to call Anthropic Claude through AWS Bedrock Runtime.
- `ollama` — calls a host-resident Ollama via `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`). No in-cluster Ollama pod is deployed.
