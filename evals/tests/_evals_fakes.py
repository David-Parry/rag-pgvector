"""In-memory fakes for retriever benchmark tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from deepeval.test_case import LLMTestCase

from rag_core.ports import Chunk, RetrievedChunk


class FakeStore:
    def __init__(self, hits: Sequence[RetrievedChunk]) -> None:
        self._hits = list(hits)
        self.search_calls: list[dict[str, Any]] = []

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        raise AssertionError("retriever benchmarks must not write to the store")

    async def similarity_search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        self.search_calls.append({"query": query, "k": k, "filter": metadata_filter})
        return self._hits[:k]


class StubJudge:
    def generate(self, prompt: str, schema: object | None = None) -> str:
        return "stub"

    async def a_generate(self, prompt: str, schema: object | None = None) -> str:
        return "stub"

    def get_model_name(self) -> str:
        return "stub-judge"


class StubMetric:
    def __init__(self, score: float) -> None:
        self.score: float | None = score
        self.observed_context_lengths: list[int] = []

    def measure(self, test_case: LLMTestCase) -> float:
        self.observed_context_lengths.append(len(test_case.retrieval_context or []))
        return self.score or 0.0


def hit(idx: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"chunk-{idx}",
        text=f"context {idx}",
        metadata={"packageId": "BILLS-115hr1625enr", "pageNumber": idx},
        score=score,
    )
