"""Small helpers for adapting retrieved chunks into DeepEval test cases."""

from __future__ import annotations

from collections.abc import Sequence

from rag_core.ports import RetrievedChunk


def to_retrieval_context(chunks: Sequence[RetrievedChunk]) -> list[str]:
    return [chunk.text for chunk in chunks]
