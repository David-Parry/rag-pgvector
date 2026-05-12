"""Domain models for the ingestion service (request/response)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request payload for ``POST /ingest``."""

    collection: str = Field(..., description="govinfo collection code (e.g. BILLS, FR, CFR)")
    last_modified_start_date: str | None = Field(
        default=None,
        alias="lastModifiedStartDate",
        description="ISO-8601 timestamp; only packages modified after this will be considered.",
    )
    last_modified_end_date: str | None = Field(
        default=None,
        alias="lastModifiedEndDate",
        description="ISO-8601 timestamp; only packages modified before this will be considered.",
    )
    page_size: int = Field(default=100, ge=1, le=1000, alias="pageSize")
    max_packages: int | None = Field(
        default=None,
        ge=1,
        alias="maxPackages",
        description="Optional cap on packages processed in a single call.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class IngestPackageRequest(BaseModel):
    """Request payload for ``POST /ingest/package`` — single-PDF ingest by packageId."""

    package_id: str = Field(
        ...,
        alias="packageId",
        min_length=1,
        description="govinfo packageId, e.g. 'BILLS-115hr1625enr' or 'FR-2018-04-12'.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class IngestResponse(BaseModel):
    """Response payload for ``POST /ingest`` and ``POST /ingest/package``."""

    ingested_chunks: int = Field(alias="ingested")
    packages: int
    skipped: int
    collection: str

    model_config = {"populate_by_name": True}
