"""``VectorStorePort`` adapter built on ``langchain_postgres.PGVectorStore``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from langchain_core.documents import Document
from langchain_postgres import Column, PGEngine, PGVectorStore

from rag_core.ports import Chunk, RetrievedChunk
from rag_core.settings import DatabaseSettings

# Schema we want for `rag_chunks`. Names overridden on `langchain-postgres`'s
# defaults so the table reads naturally:
#   id (uuid pk) | content (text) | embedding (vector(N)) | metadata (jsonb)
#   embedding_model (text) | embedding_model_version (text)
#
# The two trailing columns are *hoisted* metadata fields: PGVectorStore writes
# them from `Document.metadata[<name>]` into typed columns AND keeps them in the
# JSON blob. Hoisting lets us index/filter on them later (e.g. WHERE
# embedding_model_version = '0') without paying for JSON extraction at query
# time. They're stamped per-chunk by `add_chunks` below using the embedding
# settings injected at construction, so every row is self-describing about
# which model produced its vector.
ID_COLUMN = "id"
METADATA_JSON_COLUMN = "metadata"
EMBEDDING_MODEL_COLUMN = "embedding_model"
EMBEDDING_MODEL_VERSION_COLUMN = "embedding_model_version"


class PgVectorStoreAdapter:
    """Async adapter. Construct via ``PgVectorStoreAdapter.create(...)``.

    The constructor is private-by-convention; ``create`` is async because the
    underlying ``PGVectorStore`` requires async initialization.
    """

    def __init__(
        self,
        *,
        engine: PGEngine,
        store: PGVectorStore,
        embedding_model_name: str,
        embedding_model_version: str,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self._engine = engine
        self._store = store
        self._embedding_model_name = embedding_model_name
        self._embedding_model_version = embedding_model_version
        self._log = logger

    @classmethod
    async def create(
        cls,
        settings: DatabaseSettings,
        embedding_service: Any,
        *,
        vector_size: int,
        embedding_model_name: str,
        embedding_model_version: str,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> PgVectorStoreAdapter:
        """Create the engine + table (if needed) + vector store handle."""
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
            log.info(
                "pgvector.table_initialized",
                table=settings.collection,
                id_column=ID_COLUMN,
                metadata_json_column=METADATA_JSON_COLUMN,
                hoisted_columns=[
                    EMBEDDING_MODEL_COLUMN,
                    EMBEDDING_MODEL_VERSION_COLUMN,
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
        return cls(
            engine=engine,
            store=store,
            embedding_model_name=embedding_model_name,
            embedding_model_version=embedding_model_version,
            logger=log,
        )

    async def aclose(self) -> None:
        try:
            await self._engine.close()
        except Exception:
            self._log.debug("pgvector.engine_close_failed", exc_info=True)

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        if not chunks:
            return 0
        # Stamp the embedding model/version on every chunk so PGVectorStore
        # populates the hoisted typed columns on insert. The domain layer is
        # intentionally unaware of which embedding model is in use — that's an
        # adapter-level concern and lives here.
        docs = [
            Document(
                id=chunk.id,
                page_content=chunk.text,
                metadata={
                    **dict(chunk.metadata),
                    EMBEDDING_MODEL_COLUMN: self._embedding_model_name,
                    EMBEDDING_MODEL_VERSION_COLUMN: self._embedding_model_version,
                },
            )
            for chunk in chunks
        ]
        ids = [chunk.id for chunk in chunks]
        await self._store.aadd_documents(docs, ids=ids)
        return len(docs)

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
