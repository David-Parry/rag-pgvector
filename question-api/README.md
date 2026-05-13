# question-api

Project 2 of the rag-pgvector monorepo. A FastAPI pod that answers strictly-grounded questions over the data loaded by `vectorizer`.

## Endpoints

- `POST /ask` — body: `{ "question": "...", "metadata": {...}, "topK": 5 }`. Returns `{ "answer": "...", "citations": [...], "usedContextCount": n }`.
- `GET /healthz` — readiness probe.

## LLM provider

The service uses direct Anthropic Claude API calls. Configure `ANTHROPIC_API_KEY`
or `ANTHROPIC_API_KEY_FILE`, and optionally `ANTHROPIC_DIRECT_MODEL`.
