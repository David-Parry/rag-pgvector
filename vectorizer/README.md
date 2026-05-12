# vectorizer

Project 1 of the rag-pgvector monorepo. A long-running FastAPI pod that:

1. Lists packages from `https://api.govinfo.gov/packages`
2. Downloads each PDF
3. Extracts text per page with PyMuPDF
4. Splits with the shared `chonkie.RecursiveChunker` configured with legislative rules (SEC./TITLE/§ markers at level 0; chunk_size=1600 chars)
5. Embeds with AWS Bedrock Titan v2 (1024-dim)
6. Upserts into pgvector via `langchain-postgres`

## Endpoints

- `POST /ingest` — body: `{ "collection": "BILLS", "lastModifiedStartDate": "...", "lastModifiedEndDate": "...", "pageSize": 100, "metadata": {...} }`
- `GET /healthz` — readiness probe.

See the workspace [README](../README.md) for setup.
