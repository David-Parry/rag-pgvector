"""In-memory port fakes for vectorizer tests (importable from test modules)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from rag_core.ports import Chunk, PdfDocument, RetrievedChunk


class FakeGovInfoClient:
    def __init__(self, packages: list[Mapping[str, Any]], pdfs: dict[str, PdfDocument]) -> None:
        self.packages = packages
        self.pdfs = pdfs
        self.list_calls: list[dict[str, Any]] = []
        self.download_calls: list[str] = []

    async def list_packages(
        self,
        *,
        collection: str,
        last_modified_start: str | None = None,
        last_modified_end: str | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[Mapping[str, Any]]:
        self.list_calls.append(
            {
                "collection": collection,
                "start": last_modified_start,
                "end": last_modified_end,
                "page_size": page_size,
            }
        )
        for package in self.packages:
            yield package

    async def download_pdf(self, package_id: str) -> PdfDocument:
        self.download_calls.append(package_id)
        return self.pdfs[package_id]


class FakeLoader:
    def load(self, document: PdfDocument) -> Sequence[Chunk]:
        text_pages = document.content.decode("utf-8").split("\f")
        chunks: list[Chunk] = []
        for index, page_text in enumerate(text_pages, start=1):
            if not page_text.strip():
                continue
            chunks.append(
                Chunk(
                    id=f"{document.package_id}:p{index}",
                    text=page_text,
                    metadata={"pageNumber": index, "totalPages": len(text_pages)},
                )
            )
        return chunks


class FakeStore:
    def __init__(self) -> None:
        self.added: list[Chunk] = []

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        self.added.extend(chunks)
        return len(chunks)

    async def similarity_search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        return []
