"""In-memory port fakes for question-api tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from rag_core.ports import Chunk, RetrievedChunk


class FakeStore:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self.hits = hits
        self.search_calls: list[dict[str, Any]] = []

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        raise AssertionError("question-api domain must not write to the store")

    async def similarity_search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        self.search_calls.append({"query": query, "k": k, "filter": metadata_filter})
        return list(self.hits)


class FakeLLM:
    def __init__(self, reply: str = "fake answer") -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    async def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        self.calls.append((system, user))
        yield self.reply


def hit(idx: int, score: float, *, package: str = "PKG-1") -> RetrievedChunk:
    return RetrievedChunk(
        id=f"chunk-{idx}",
        text=f"context number {idx}",
        metadata={
            "packageId": package,
            "sourceUrl": f"https://example.gov/{package}",
            "pageNumber": idx,
        },
        score=score,
    )
