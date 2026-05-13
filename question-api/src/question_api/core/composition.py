"""IoC composition root for the question-api service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from question_api.adapters.anthropic_llm import AnthropicLLMAdapter
from question_api.adapters.pgvector_retriever import PgVectorRetrieverAdapter
from question_api.adapters.titan_embeddings import TitanEmbeddingsAdapter
from question_api.domain.ask_service import AskService
from rag_core.ports import LLMPort

if TYPE_CHECKING:
    from question_api.core.settings import QuestionApiSettings


@dataclass(slots=True)
class Container:
    settings: QuestionApiSettings
    embeddings: TitanEmbeddingsAdapter
    retriever: PgVectorRetrieverAdapter
    llm: LLMPort
    service: AskService

    async def aclose(self) -> None:
        await self.retriever.aclose()


async def build_container(settings: QuestionApiSettings) -> Container:
    log = structlog.get_logger("question_api")
    embeddings = TitanEmbeddingsAdapter(settings.aws)
    retriever = await PgVectorRetrieverAdapter.create(
        settings.database,
        embedding_service=embeddings.langchain_embeddings,
        vector_size=settings.aws.embedding_dimensions,
        logger=log,
    )

    llm: LLMPort = AnthropicLLMAdapter(settings.anthropic)

    service = AskService(
        store=retriever,
        llm=llm,
        retrieval=settings.retrieval,
        provider_name=AnthropicLLMAdapter.PROVIDER,
        logger=log,
    )
    return Container(
        settings=settings,
        embeddings=embeddings,
        retriever=retriever,
        llm=llm,
        service=service,
    )
