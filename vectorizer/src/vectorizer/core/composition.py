"""IoC composition root for the vectorizer service.

This is the *only* module that knows about concrete adapter classes. The API
layer and the domain layer both consume the resulting ``Container`` via
FastAPI dependency injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
import structlog

from rag_core.chunking import build_text_splitter
from vectorizer.adapters.govinfo_client import GovInfoClient
from vectorizer.adapters.pdf_loader import PyMuPdfLoader
from vectorizer.adapters.pgvector_store import PgVectorStoreAdapter
from vectorizer.adapters.titan_embeddings import TitanEmbeddingsAdapter
from vectorizer.domain.vectorize_service import VectorizeService

if TYPE_CHECKING:
    from vectorizer.core.settings import VectorizerSettings


@dataclass(slots=True)
class Container:
    """Fully wired dependency graph for the service lifetime."""

    settings: VectorizerSettings
    govinfo: GovInfoClient
    embeddings: TitanEmbeddingsAdapter
    store: PgVectorStoreAdapter
    service: VectorizeService

    async def aclose(self) -> None:
        await self.govinfo.aclose()
        await self.store.aclose()


async def build_container(settings: VectorizerSettings) -> Container:
    """Construct adapters and inject them into the domain service."""
    log = structlog.get_logger("vectorizer")
    http_client = httpx.AsyncClient(
        base_url=settings.govinfo.base_url,
        timeout=httpx.Timeout(60.0),
    )
    govinfo = GovInfoClient(settings.govinfo, client=http_client, logger=log)
    embeddings = TitanEmbeddingsAdapter(settings.aws)
    store = await PgVectorStoreAdapter.create(
        settings.database,
        embedding_service=embeddings.langchain_embeddings,
        vector_size=settings.aws.embedding_dimensions,
        embedding_model_name=settings.aws.embedding_model_name,
        embedding_model_version=settings.aws.embedding_model_version,
        logger=log,
    )
    loader = PyMuPdfLoader(logger=log)
    service = VectorizeService(
        govinfo=govinfo,
        loader=loader,
        splitter=build_text_splitter(),
        store=store,
        logger=log,
    )
    return Container(
        settings=settings,
        govinfo=govinfo,
        embeddings=embeddings,
        store=store,
        service=service,
    )
