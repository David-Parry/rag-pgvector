"""Narrow ``Protocol`` ports that the domain layer depends on.

These interfaces are deliberately small (Interface Segregation) and free of
framework specifics. Concrete adapters live next to each app and are wired into
the composition root via constructor injection (Dependency Inversion).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Chunk:
    """A unit of text with associated metadata, ready to be embedded and stored."""

    id: str
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned from a vector-store similarity search, with its score."""

    id: str
    text: str
    metadata: Mapping[str, Any]
    score: float


@dataclass(frozen=True, slots=True)
class PdfDocument:
    """A downloaded PDF held in memory together with its provenance metadata."""

    package_id: str
    title: str
    source_url: str
    content: bytes
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class EmbeddingsPort(Protocol):
    """Embeds text into dense vectors. Adapters: Bedrock Titan v2."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents. Order in == order out."""
        ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Persists and queries chunk embeddings. Adapters: pgvector via langchain-postgres."""

    async def add_chunks(self, chunks: Sequence[Chunk]) -> int:
        """Upsert chunks (idempotent on ``Chunk.id``). Returns the number written."""
        ...

    async def similarity_search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k chunks most similar to ``query``, optionally filtered by metadata."""
        ...


@runtime_checkable
class DocumentLoaderPort(Protocol):
    """Extracts plain-text pages from a PDF blob. Adapters: PyMuPDF."""

    def load(self, document: PdfDocument) -> Sequence[Chunk]:
        """Return one ``Chunk`` per page (pre-splitter)."""
        ...


@runtime_checkable
class LLMPort(Protocol):
    """Generates a final answer from system + user messages. Adapters: Anthropic, Ollama."""

    async def generate(self, system: str, user: str) -> str:
        """Return the model's reply as a single string."""
        ...

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        """Yield streaming tokens. Default adapters may simulate via ``generate``."""
        ...


@runtime_checkable
class GovInfoClientPort(Protocol):
    """Fetches package listings and PDF blobs from api.govinfo.gov."""

    async def list_packages(
        self,
        *,
        collection: str,
        last_modified_start: str | None = None,
        last_modified_end: str | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[Mapping[str, Any]]:
        """Yield package summary dicts (one per package)."""
        ...

    async def download_pdf(self, package_id: str) -> PdfDocument:
        """Download the PDF rendition for ``package_id``."""
        ...
