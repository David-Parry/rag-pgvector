"""Shared fixtures for vectorizer tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from _vectorizer_fakes import FakeGovInfoClient, FakeLoader, FakeStore

from rag_core.chunking import TextSplitter, build_text_splitter
from rag_core.ports import PdfDocument


@pytest.fixture
def small_splitter() -> TextSplitter:
    return build_text_splitter(chunk_size=80)


@pytest.fixture
def fake_loader() -> FakeLoader:
    return FakeLoader()


@pytest.fixture
def fake_store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def make_pdf():
    def _factory(package_id: str, pages: list[str]) -> PdfDocument:
        return PdfDocument(
            package_id=package_id,
            title=f"Title for {package_id}",
            source_url=f"https://example.gov/{package_id}.pdf",
            content="\f".join(pages).encode("utf-8"),
            metadata={"docClass": "test"},
        )

    return _factory


@pytest.fixture
def make_govinfo():
    def _factory(
        packages: list[Mapping[str, Any]],
        pdfs: dict[str, PdfDocument],
    ) -> FakeGovInfoClient:
        return FakeGovInfoClient(packages=packages, pdfs=pdfs)

    return _factory
