# rag-core

Shared library for the rag-pgvector monorepo. Contains:

- `ports`: `Protocol` interfaces (Embeddings, VectorStore, DocumentLoader, LLM, GovInfoClient).
- `prompts`: the strictly-grounded QA system prompt and the user-prompt builder.
- `chunking`: the shared `chonkie.RecursiveChunker` factory configured with US legislative drafting markers (SEC., TITLE, §, etc.) as level-0 boundaries, behind a small `TextSplitter` Protocol.
- `settings`: Pydantic-Settings base classes for env-driven configuration.
- `logging`: structlog setup helper.

The library has zero framework dependencies (no FastAPI, no httpx, no boto3) so domain code can depend on it freely.
