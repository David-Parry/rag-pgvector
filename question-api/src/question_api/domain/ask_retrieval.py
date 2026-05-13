"""Shared retrieval helpers for ask flow (thresholding and citation shaping)."""

from __future__ import annotations

from collections.abc import Sequence

from question_api.domain.models import Citation
from rag_core.ports import RetrievedChunk

_SNIPPET_CHARS = 280


def filter_chunks_by_threshold(
    hits: Sequence[RetrievedChunk],
    *,
    threshold: float,
) -> list[RetrievedChunk]:
    """Cosine *distance* in pgvector: lower = more similar. Drop above-threshold."""
    return [hit for hit in hits if hit.score <= threshold]


def chunks_to_citations(chunks: Sequence[RetrievedChunk]) -> list[Citation]:
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
