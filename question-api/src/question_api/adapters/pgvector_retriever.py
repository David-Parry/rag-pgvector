"""``VectorStorePort`` adapter for query-time retrieval over pgvector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from langchain_postgres import Column, PGEngine, PGVectorStore

from rag_core.ports import Chunk, RetrievedChunk
from rag_core.settings import DatabaseSettings

# Column layout MUST match the vectorizer side or PGVectorStore will fail to
# project the rows. The two hoisted metadata columns ride along on every read,
# surfacing in `RetrievedChunk.metadata` so callers (citations, audit logs)
# can see which embedding model was responsible for each retrieved row.
ID_COLUMN = "id"
METADATA_JSON_COLUMN = "metadata"
EMBEDDING_MODEL_COLUMN = "embedding_model"
EMBEDDING_MODEL_VERSION_COLUMN = "embedding_model_version"


class PgVectorRetrieverAdapter:
    """Read-side adapter; ``add_chunks`` is a no-op for this side and raises."""

    def __init__(
        self,
        *,
        engine: PGEngine,
        store: PGVectorStore,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self._engine = engine
        self._store = store
        self._log = logger

    @classmethod
    async def create(
        cls,
        settings: DatabaseSettings,
        embedding_service: Any,
        *,
        vector_size: int,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> PgVectorRetrieverAdapter:
        log = logger or structlog.get_logger(__name__)
        engine = PGEngine.from_connection_string(url=settings.url)
        try:
            await engine.ainit_vectorstore_table(
                table_name=settings.collection,
                vector_size=vector_size,
                id_column=ID_COLUMN,
                metadata_json_column=METADATA_JSON_COLUMN,
                metadata_columns=[
                    Column(EMBEDDING_MODEL_COLUMN, "TEXT"),
                    Column(EMBEDDING_MODEL_VERSION_COLUMN, "TEXT"),
                ],
            )
        except Exception as exc:
            log.debug("pgvector.table_init_skipped", error=str(exc))
        store = await PGVectorStore.create(
            engine=engine,
            table_name=settings.collection,
            embedding_service=embedding_service,
            id_column=ID_COLUMN,
            metadata_json_column=METADATA_JSON_COLUMN,
            metadata_columns=[
                EMBEDDING_MODEL_COLUMN,
                EMBEDDING_MODEL_VERSION_COLUMN,
            ],
        )
        return cls(engine=engine, store=store, logger=log)

    async def aclose(self) -> None:
        try:
            await self._engine.close()
        except Exception:
            self._log.debug("pgvector.engine_close_failed", exc_info=True)

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        raise NotImplementedError(
            "question-api is read-only; use the vectorizer service to add chunks."
        )

    async def similarity_search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        results = await self._store.asimilarity_search_with_score(
            query,
            k=k,
            filter=dict(metadata_filter) if metadata_filter else None,
        )
        retrieved: list[RetrievedChunk] = []
        for document, score in results:
            doc_id = getattr(document, "id", None) or document.metadata.get("id") or ""
            retrieved.append(
                RetrievedChunk(
                    id=str(doc_id),
                    text=document.page_content,
                    metadata=dict(document.metadata),
                    score=float(score),
                )
            )
        return retrieved
