"""``DocumentLoaderPort`` adapter using PyMuPDF (``fitz``).

We intentionally do *not* use ``langchain_community.PyMuPDFLoader`` here:
it requires a filesystem path, but our pipeline holds the PDF bytes in memory.
PyMuPDF's ``fitz.open(stream=...)`` is the canonical zero-copy path.
"""

from __future__ import annotations

from collections.abc import Sequence

import fitz  # type: ignore[import-untyped]
import structlog

from rag_core.ports import Chunk, PdfDocument


class PyMuPdfLoader:
    """One ``Chunk`` per page; the splitter further subdivides downstream."""

    def __init__(self, *, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self._log = logger or structlog.get_logger(__name__)

    def load(self, document: PdfDocument) -> Sequence[Chunk]:
        chunks: list[Chunk] = []
        with fitz.open(stream=document.content, filetype="pdf") as pdf:
            for page_index in range(pdf.page_count):
                page = pdf.load_page(page_index)
                text = page.get_text("text") or ""
                if not text.strip():
                    continue
                chunks.append(
                    Chunk(
                        id=f"{document.package_id}:p{page_index + 1}",
                        text=text,
                        metadata={
                            "pageNumber": page_index + 1,
                            "totalPages": pdf.page_count,
                        },
                    )
                )
        self._log.debug(
            "pdf.loaded",
            package_id=document.package_id,
            pages=len(chunks),
        )
        return chunks
