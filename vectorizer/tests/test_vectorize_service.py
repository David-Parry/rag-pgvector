from __future__ import annotations

import pytest
from _vectorizer_fakes import FakeStore

from vectorizer.domain.models import IngestPackageRequest, IngestRequest
from vectorizer.domain.vectorize_service import VectorizeService


@pytest.mark.asyncio
async def test_ingest_writes_chunks_with_stable_metadata(
    small_splitter, fake_loader, fake_store, make_pdf, make_govinfo
) -> None:
    pages = ["alpha " * 30, "beta " * 30, "gamma " * 30]
    pdf = make_pdf("PKG-1", pages)
    govinfo = make_govinfo([{"packageId": "PKG-1"}], {"PKG-1": pdf})
    service = VectorizeService(
        govinfo=govinfo,
        loader=fake_loader,
        splitter=small_splitter,
        store=fake_store,
    )

    response = await service.ingest(
        IngestRequest(collection="BILLS", pageSize=50, metadata={"tag": "demo"})
    )

    assert response.packages == 1
    assert response.skipped == 0
    assert response.ingested_chunks == len(fake_store.added)
    assert response.ingested_chunks > 0
    chunk = fake_store.added[0]
    assert chunk.metadata["packageId"] == "PKG-1"
    assert chunk.metadata["sourceUrl"] == "https://example.gov/PKG-1.pdf"
    assert chunk.metadata["title"] == "Title for PKG-1"
    assert chunk.metadata["tag"] == "demo"
    assert "ingestedAt" in chunk.metadata
    assert chunk.metadata["pageNumber"] in {1, 2, 3}
    assert isinstance(chunk.metadata["chunkIndex"], int)


@pytest.mark.asyncio
async def test_ingest_is_deterministic_on_chunk_ids(
    small_splitter, fake_loader, make_pdf, make_govinfo
) -> None:
    pdf = make_pdf("PKG-2", ["payload " * 40])

    store_a = FakeStore()
    service_a = VectorizeService(
        govinfo=make_govinfo([{"packageId": "PKG-2"}], {"PKG-2": pdf}),
        loader=fake_loader,
        splitter=small_splitter,
        store=store_a,
    )
    res1 = await service_a.ingest(IngestRequest(collection="BILLS"))

    store_b = FakeStore()
    service_b = VectorizeService(
        govinfo=make_govinfo([{"packageId": "PKG-2"}], {"PKG-2": pdf}),
        loader=fake_loader,
        splitter=small_splitter,
        store=store_b,
    )
    res2 = await service_b.ingest(IngestRequest(collection="BILLS"))

    assert res1.ingested_chunks == res2.ingested_chunks
    ids_a = sorted(c.id for c in store_a.added)
    ids_b = sorted(c.id for c in store_b.added)
    assert ids_a == ids_b
    assert len(set(ids_a)) == len(ids_a)


@pytest.mark.asyncio
async def test_ingest_skips_packages_without_id(
    small_splitter, fake_loader, fake_store, make_pdf, make_govinfo
) -> None:
    govinfo = make_govinfo(
        [{"packageId": ""}, {"foo": "bar"}, {"packageId": "PKG-3"}],
        {"PKG-3": make_pdf("PKG-3", ["only one page " * 20])},
    )
    service = VectorizeService(
        govinfo=govinfo,
        loader=fake_loader,
        splitter=small_splitter,
        store=fake_store,
    )
    response = await service.ingest(IngestRequest(collection="BILLS"))

    assert response.packages == 1
    assert response.skipped == 2
    assert govinfo.download_calls == ["PKG-3"]


@pytest.mark.asyncio
async def test_ingest_respects_max_packages(
    small_splitter, fake_loader, fake_store, make_pdf, make_govinfo
) -> None:
    pdfs = {f"P{i}": make_pdf(f"P{i}", ["x " * 50]) for i in range(5)}
    govinfo = make_govinfo([{"packageId": pid} for pid in pdfs], pdfs)
    service = VectorizeService(
        govinfo=govinfo,
        loader=fake_loader,
        splitter=small_splitter,
        store=fake_store,
    )

    response = await service.ingest(IngestRequest(collection="BILLS", maxPackages=2))
    assert response.packages == 2
    assert len(govinfo.download_calls) == 2


@pytest.mark.asyncio
async def test_ingest_package_writes_chunks_for_single_package_id(
    small_splitter, fake_loader, fake_store, make_pdf, make_govinfo
) -> None:
    pdf = make_pdf("BILLS-115hr1625enr", ["alpha " * 30, "beta " * 30])
    govinfo = make_govinfo([], {"BILLS-115hr1625enr": pdf})
    service = VectorizeService(
        govinfo=govinfo,
        loader=fake_loader,
        splitter=small_splitter,
        store=fake_store,
    )

    response = await service.ingest_package(
        IngestPackageRequest(
            packageId="BILLS-115hr1625enr",
            metadata={"source": "manual"},
        )
    )

    assert response.packages == 1
    assert response.skipped == 0
    assert response.collection == "BILLS"
    assert response.ingested_chunks == len(fake_store.added) > 0
    assert govinfo.list_calls == []
    assert govinfo.download_calls == ["BILLS-115hr1625enr"]
    chunk = fake_store.added[0]
    assert chunk.metadata["packageId"] == "BILLS-115hr1625enr"
    assert chunk.metadata["source"] == "manual"


@pytest.mark.asyncio
async def test_ingest_package_reports_skipped_on_download_failure(
    small_splitter, fake_loader, fake_store, make_govinfo
) -> None:
    govinfo = make_govinfo([], {})
    service = VectorizeService(
        govinfo=govinfo,
        loader=fake_loader,
        splitter=small_splitter,
        store=fake_store,
    )

    response = await service.ingest_package(
        IngestPackageRequest(packageId="BILLS-does-not-exist")
    )

    assert response.packages == 0
    assert response.skipped == 1
    assert response.ingested_chunks == 0
    assert response.collection == "BILLS"
    assert fake_store.added == []
