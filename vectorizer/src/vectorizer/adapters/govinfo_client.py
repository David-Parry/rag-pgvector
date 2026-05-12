"""``GovInfoClientPort`` adapter against https://api.govinfo.gov/packages."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from types import TracebackType
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from rag_core.ports import PdfDocument
from rag_core.settings import GovInfoSettings


class GovInfoClient:
    """Async client. Implements ``GovInfoClientPort`` structurally."""

    def __init__(
        self,
        settings: GovInfoSettings,
        *,
        client: httpx.AsyncClient | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(60.0),
        )
        self._owns_client = client is None
        self._log = logger or structlog.get_logger(__name__)

    async def __aenter__(self) -> GovInfoClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_packages(
        self,
        *,
        collection: str,
        last_modified_start: str | None = None,
        last_modified_end: str | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[Mapping[str, Any]]:
        """Yield package summaries from /packages, paging via nextPage."""
        offset_mark: str | None = "*"
        params: dict[str, Any] = {
            "api_key": self._settings.api_key.get_secret_value(),
            "pageSize": page_size,
        }
        if last_modified_start is not None:
            params["lastModifiedStartDate"] = last_modified_start
        if last_modified_end is not None:
            params["lastModifiedEndDate"] = last_modified_end

        while offset_mark is not None:
            page_params = {**params, "offsetMark": offset_mark}
            data = await self._get_json(
                f"/collections/{collection}",
                params=page_params,
            )
            for package in data.get("packages", []) or []:
                if isinstance(package, dict):
                    yield package
            offset_mark = data.get("nextPage") or None
            if isinstance(offset_mark, str) and offset_mark.startswith("http"):
                offset_mark = self._extract_offset_mark(offset_mark)

    async def download_pdf(self, package_id: str) -> PdfDocument:
        """Download the PDF rendition for a package and pull a title from /summary."""
        summary_task = self._get_json(
            f"/packages/{package_id}/summary",
            params={"api_key": self._settings.api_key.get_secret_value()},
        )
        summary = await summary_task
        title = (
            summary.get("title")
            or summary.get("documentTitle")
            or package_id
        )

        pdf_url = f"/packages/{package_id}/pdf"
        content = await self._get_bytes(
            pdf_url,
            params={"api_key": self._settings.api_key.get_secret_value()},
        )
        absolute_url = str(httpx.URL(self._settings.base_url).join(pdf_url))
        return PdfDocument(
            package_id=package_id,
            title=str(title),
            source_url=absolute_url,
            content=content,
            metadata={k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool))},
        )

    async def _get_json(self, path: str, *, params: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request_with_retry("GET", path, params=params)
        return response.json()

    async def _get_bytes(self, path: str, *, params: Mapping[str, Any]) -> bytes:
        response = await self._request_with_retry(
            "GET",
            path,
            params=params,
            follow_redirects=True,
        )
        return response.content

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any],
        follow_redirects: bool = False,
    ) -> httpx.Response:
        attempts = AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(
                (httpx.TransportError, httpx.HTTPStatusError),
            ),
            reraise=True,
        )
        try:
            async for attempt in attempts:
                with attempt:
                    response = await self._client.request(
                        method,
                        path,
                        params=params,
                        follow_redirects=follow_redirects,
                    )
                    if response.status_code >= 500 or response.status_code == 429:
                        response.raise_for_status()
                    response.raise_for_status()
                    return response
        except RetryError as retry_err:
            inner = retry_err.last_attempt.exception()
            if inner is not None:
                raise inner from retry_err
            raise
        raise RuntimeError("unreachable")

    @staticmethod
    def _extract_offset_mark(url: str) -> str | None:
        """``nextPage`` may be returned as a full URL; pull just the offsetMark param."""
        parsed = httpx.URL(url)
        return parsed.params.get("offsetMark") or None
