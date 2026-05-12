# question-api

Project 2 of the rag-pgvector monorepo. A FastAPI pod that answers strictly-grounded questions over the data loaded by `vectorizer`.

## Endpoints

- `POST /ask` — body: `{ "question": "...", "metadata": {...}, "topK": 5 }`. Returns `{ "answer": "...", "citations": [...], "usedContextCount": n }`.
- `GET /healthz` — readiness probe.

## LLM provider

Selected via `LLM_PROVIDER`:

- `anthropic` (default) — uses `ANTHROPIC_API_KEY`, model `claude-sonnet-4-5`.
- `ollama` — calls a host-resident Ollama via `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`). No in-cluster Ollama pod is deployed.
