"""IoC composition root for the question-api service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from question_api.adapters.anthropic_llm import AnthropicLLMAdapter
from question_api.adapters.pgvector_retriever import PgVectorRetrieverAdapter
from question_api.adapters.titan_embeddings import TitanEmbeddingsAdapter
from question_api.core.langgraph_redis_settings import sanitize_redis_url_for_log
from question_api.domain.ask_graph import compile_ask_graph
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
    checkpointer: AsyncRedisSaver

    async def aclose(self) -> None:
        await self.retriever.aclose()
        await self.checkpointer.__aexit__(None, None, None)


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

    checkpointer = AsyncRedisSaver(
        redis_url=settings.langgraph_redis.redis_url,
        ttl=settings.langgraph_redis.ttl_config(),
    )
    await checkpointer.__aenter__()
    try:
        redis_endpoint = sanitize_redis_url_for_log(settings.langgraph_redis.redis_url)
        log.info(
            "question_api.langgraph_session_memory",
            session_memory_backend="redis",
            session_memory_endpoint=redis_endpoint,
            checkpointer_cls=type(checkpointer).__name__,
            note="Per-chat history and ACA turn list are persisted in Redis for thread_id=sessionId.",
        )
        graph = compile_ask_graph(
            store=retriever,
            llm=llm,
            retrieval=settings.retrieval,
            provider_name=AnthropicLLMAdapter.PROVIDER,
            checkpointer=checkpointer,
            logger=log,
            session_memory_backend="redis",
            session_memory_endpoint=redis_endpoint,
        )
        service = AskService(
            graph=graph,
            store=retriever,
            llm=llm,
            retrieval=settings.retrieval,
            provider_name=AnthropicLLMAdapter.PROVIDER,
            logger=log,
            session_memory_backend="redis",
            session_memory_endpoint=redis_endpoint,
        )
        return Container(
            settings=settings,
            embeddings=embeddings,
            retriever=retriever,
            llm=llm,
            service=service,
            checkpointer=checkpointer,
        )
    except BaseException:
        await checkpointer.__aexit__(None, None, None)
        raise
