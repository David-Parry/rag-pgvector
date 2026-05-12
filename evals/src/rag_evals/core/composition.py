"""IoC composition for the retriever benchmark CLI and integration tests."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from question_api.adapters.pgvector_retriever import PgVectorRetrieverAdapter
from question_api.adapters.titan_embeddings import TitanEmbeddingsAdapter

from rag_evals.adapters.deepeval_judge import DeepEvalJudgeAdapter
from rag_evals.core.settings import EvalsSettings
from rag_evals.domain.benchmark import RetrieverBenchmark


@dataclass(slots=True)
class Container:
    settings: EvalsSettings
    embeddings: TitanEmbeddingsAdapter
    retriever: PgVectorRetrieverAdapter
    judge: DeepEvalJudgeAdapter
    benchmark: RetrieverBenchmark

    async def aclose(self) -> None:
        await self.retriever.aclose()


async def build_container(settings: EvalsSettings) -> Container:
    log = structlog.get_logger("rag_evals")
    embeddings = TitanEmbeddingsAdapter(settings.aws)
    retriever = await PgVectorRetrieverAdapter.create(
        settings.database,
        embedding_service=embeddings.langchain_embeddings,
        vector_size=settings.aws.embedding_dimensions,
        logger=log,
    )
    judge = DeepEvalJudgeAdapter(
        provider=settings.deepeval.judge_provider,
        anthropic=settings.anthropic,
        ollama=settings.ollama,
    )
    benchmark = RetrieverBenchmark(store=retriever, judge=judge, logger=log)
    return Container(
        settings=settings,
        embeddings=embeddings,
        retriever=retriever,
        judge=judge,
        benchmark=benchmark,
    )
