from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import SecretStr

from rag_core.settings import GovInfoSettings
from vectorizer.adapters.govinfo_client import GovInfoClient


def _settings() -> GovInfoSettings:
    return GovInfoSettings(
        GOVINFO_API_KEY=SecretStr("test-key"),
        GOVINFO_BASE_URL="https://api.govinfo.gov",
    )


@pytest.mark.asyncio
@respx.mock
async def test_list_packages_paginates_via_offset_mark() -> None:
    page_one = respx.get("https://api.govinfo.gov/collections/BILLS").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "packages": [{"packageId": "P1"}, {"packageId": "P2"}],
                    "nextPage": "https://api.govinfo.gov/collections/BILLS?offsetMark=ABC",
                },
            ),
            httpx.Response(
                200,
                json={"packages": [{"packageId": "P3"}], "nextPage": None},
            ),
        ]
    )

    async with GovInfoClient(_settings()) as client:
        seen = [pkg["packageId"] async for pkg in client.list_packages(collection="BILLS")]

    assert seen == ["P1", "P2", "P3"]
    assert page_one.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_download_pdf_combines_summary_and_pdf() -> None:
    respx.get("https://api.govinfo.gov/packages/P1/summary").mock(
        return_value=httpx.Response(
            200,
            json={"title": "Big Bill", "branch": "legislative"},
        )
    )
    respx.get("https://api.govinfo.gov/packages/P1/pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 fake")
    )

    async with GovInfoClient(_settings()) as client:
        document = await client.download_pdf("P1")

    assert document.package_id == "P1"
    assert document.title == "Big Bill"
    assert document.content.startswith(b"%PDF")
    assert document.source_url.endswith("/packages/P1/pdf")
    assert document.metadata["branch"] == "legislative"
