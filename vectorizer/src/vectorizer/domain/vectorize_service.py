"""Orchestrator for the vectorization pipeline.

Depends only on Protocol ports — no HTTP, DB, or PDF library imports here.
This is the only place that knows the *order* of operations:

    list packages -> download pdf -> load pages -> split -> add chunks
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from rag_core.chunking import TextSplitter
from rag_core.ports import (
    Chunk,
    DocumentLoaderPort,
    GovInfoClientPort,
    PdfDocument,
    VectorStorePort,
)
from vectorizer.domain.models import (
    IngestPackageRequest,
    IngestRequest,
    IngestResponse,
)


class IngestPackageDownloadError(RuntimeError):
    """A requested single-package ingest could not download its govinfo source."""


class VectorizeService:
    """Pipeline: govinfo -> PyMuPDF -> splitter -> pgvector. Pure orchestration."""

    def __init__(
        self,
        *,
        govinfo: GovInfoClientPort,
        loader: DocumentLoaderPort,
        splitter: TextSplitter,
        store: VectorStorePort,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        self._govinfo = govinfo
        self._loader = loader
        self._splitter = splitter
        self._store = store
        self._log = logger or structlog.get_logger(__name__)

    async def ingest(self, request: IngestRequest) -> IngestResponse:
        """Run the full pipeline for a single ``IngestRequest``."""
        log = self._log.bind(collection=request.collection)
        log.info("ingest.start", page_size=request.page_size, max_packages=request.max_packages)

        package_count = 0
        chunk_count = 0
        skipped = 0

        async for package in self._govinfo.list_packages(
            collection=request.collection,
            last_modified_start=request.last_modified_start_date,
            last_modified_end=request.last_modified_end_date,
            page_size=request.page_size,
        ):
            if request.max_packages is not None and package_count >= request.max_packages:
                break

            package_id_raw = package.get("packageId")
            if not isinstance(package_id_raw, str) or not package_id_raw:
                skipped += 1
                continue
            package_id = package_id_raw

            try:
                pdf = await self._govinfo.download_pdf(package_id)
            except Exception as exc:
                log.warning("ingest.download_failed", package_id=package_id, error=str(exc))
                skipped += 1
                continue

            chunks = self._chunkify(pdf, user_metadata=request.metadata)
            if not chunks:
                skipped += 1
                continue

            written = await self._store.add_chunks(chunks)
            chunk_count += written
            package_count += 1
            log.info(
                "ingest.package_done",
                package_id=package_id,
                chunks_written=written,
                running_total=chunk_count,
            )

        log.info(
            "ingest.complete",
            packages=package_count,
            chunks=chunk_count,
            skipped=skipped,
        )
        return IngestResponse(
            ingested=chunk_count,
            packages=package_count,
            skipped=skipped,
            collection=request.collection,
        )

    async def ingest_package(self, request: IngestPackageRequest) -> IngestResponse:
        """Run the pipeline for a single ``packageId`` (skips the collection scan)."""
        package_id = request.package_id
        collection = _collection_from_package_id(package_id)
        log = self._log.bind(package_id=package_id, collection=collection)
        log.info("ingest_package.start")

        try:
            pdf = await self._govinfo.download_pdf(package_id)
        except Exception as exc:
            log.warning("ingest_package.download_failed", error=str(exc))
            raise IngestPackageDownloadError(
                f"Could not download govinfo package {package_id}: {exc}"
            ) from exc

        chunks = self._chunkify(pdf, user_metadata=request.metadata)
        if not chunks:
            log.warning("ingest_package.empty_pdf")
            return IngestResponse(
                ingested=0,
                packages=0,
                skipped=1,
                collection=collection,
            )

        written = await self._store.add_chunks(chunks)
        log.info("ingest_package.complete", chunks_written=written)
        return IngestResponse(
            ingested=written,
            packages=1,
            skipped=0,
            collection=collection,
        )

    def _chunkify(
        self,
        pdf: PdfDocument,
        *,
        user_metadata: Mapping[str, Any],
    ) -> list[Chunk]:
        """Apply page extraction + splitter + metadata enrichment."""
        page_chunks = self._loader.load(pdf)
        ingested_at = datetime.now(tz=UTC).isoformat()
        base_meta: dict[str, Any] = {
            "packageId": pdf.package_id,
            "title": pdf.title,
            "sourceUrl": pdf.source_url,
            "ingestedAt": ingested_at,
            **dict(pdf.metadata),
            **dict(user_metadata),
        }
        return list(self._split_pages(page_chunks, base_meta=base_meta))

    def _split_pages(
        self,
        page_chunks: Sequence[Chunk],
        *,
        base_meta: Mapping[str, Any],
    ) -> Iterable[Chunk]:
        """Split per-page text into model-sized chunks with stable ids."""
        for page_chunk in page_chunks:
            page_number = int(page_chunk.metadata.get("pageNumber", 0))
            page_text = page_chunk.text
            if not page_text.strip():
                continue
            splits = self._splitter.split_text(page_text)
            for chunk_index, split_text in enumerate(splits):
                stable_id = _deterministic_chunk_id(
                    package_id=str(base_meta["packageId"]),
                    page_number=page_number,
                    chunk_index=chunk_index,
                )
                metadata: dict[str, Any] = {
                    **base_meta,
                    "pageNumber": page_number,
                    "chunkIndex": chunk_index,
                }
                yield Chunk(id=stable_id, text=split_text, metadata=metadata)


_CHUNK_ID_NAMESPACE = uuid.UUID("d4b8e1d2-7c5a-5e8d-9b1c-1f3a8c2e4d5e")


def _deterministic_chunk_id(*, package_id: str, page_number: int, chunk_index: int) -> str:
    """``uuidv5(NS, packageId|page|chunkIndex)`` for idempotent upserts.

    The pgvector ``id`` column is typed UUID, so the chunk id must be a valid
    UUID. UUIDv5 gives us a stable (namespace, name) -> UUID mapping,
    preserving the deterministic-upsert property of the previous SHA-256-hex
    implementation while producing a value Postgres accepts directly.
    """
    name = f"{package_id}|{page_number}|{chunk_index}"
    return str(uuid.uuid5(_CHUNK_ID_NAMESPACE, name))


def _collection_from_package_id(package_id: str) -> str:
    """govinfo packageIds are conventionally ``<COLLECTION>-<rest>``.

    Falls back to the full id when no separator is present so the response
    contract (``collection`` is always populated) is preserved.
    """
    head, sep, _ = package_id.partition("-")
    return head if sep else package_id
