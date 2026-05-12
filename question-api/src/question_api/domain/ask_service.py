"""Orchestrator for the strictly-grounded ask flow.

Pure orchestration — no HTTP, DB, or LLM SDK imports. Depends only on
``rag_core.ports`` Protocols and ``rag_core.prompts`` for the system prompt.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from question_api.domain.models import AskRequest, AskResponse, Citation
from rag_core.ports import LLMPort, RetrievedChunk, VectorStorePort
from rag_core.prompts import SYSTEM_PROMPT_QA, build_user_prompt
from rag_core.settings import RetrievalSettings

_INSUFFICIENT_CONTEXT_REPLY = "I don't know based on the provided context."
_SNIPPET_CHARS = 280


class AskService:
    """retrieve -> threshold -> ground -> generate."""

    def __init__(
        self,
        *,
        store: VectorStorePort,
        llm: LLMPort,
        retrieval: RetrievalSettings,
        provider_name: str,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        self._store = store
        self._llm = llm
        self._retrieval = retrieval
        self._provider_name = provider_name
        self._log = logger or structlog.get_logger(__name__)

    async def ask(self, request: AskRequest) -> AskResponse:
        top_k = request.top_k or self._retrieval.top_k
        threshold = (
            request.score_threshold
            if request.score_threshold is not None
            else self._retrieval.score_threshold
        )
        log = self._log.bind(top_k=top_k, threshold=threshold, provider=self._provider_name)

        hits = await self._store.similarity_search(
            request.question,
            k=top_k,
            metadata_filter=request.metadata or None,
        )
        kept = self._apply_threshold(hits, threshold=threshold)
        log.info("ask.retrieved", returned=len(hits), kept=len(kept))

        if not kept:
            return AskResponse(
                answer=_INSUFFICIENT_CONTEXT_REPLY,
                citations=[],
                used_context_count=0,
                provider=self._provider_name,
            )

        user_prompt = build_user_prompt(request.question, kept)
        answer = await self._llm.generate(SYSTEM_PROMPT_QA, user_prompt)
        return AskResponse(
            answer=answer,
            citations=_to_citations(kept),
            used_context_count=len(kept),
            provider=self._provider_name,
        )

    @staticmethod
    def _apply_threshold(
        hits: Sequence[RetrievedChunk],
        *,
        threshold: float,
    ) -> list[RetrievedChunk]:
        """Cosine *distance* in pgvector: lower = more similar. Drop above-threshold."""
        return [hit for hit in hits if hit.score <= threshold]


def _to_citations(chunks: Sequence[RetrievedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for chunk in chunks:
        snippet = chunk.text.strip().replace("\n", " ")
        if len(snippet) > _SNIPPET_CHARS:
            snippet = snippet[:_SNIPPET_CHARS].rstrip() + "..."
        page_number_value = chunk.metadata.get("pageNumber")
        page_number: int | None
        try:
            page_number = int(page_number_value) if page_number_value is not None else None
        except (TypeError, ValueError):
            page_number = None
        citations.append(
            Citation(
                packageId=str(chunk.metadata.get("packageId", "unknown")),
                sourceUrl=str(chunk.metadata.get("sourceUrl", "unknown")),
                pageNumber=page_number,
                score=chunk.score,
                snippet=snippet,
            )
        )
    return citations
