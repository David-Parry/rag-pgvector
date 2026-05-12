"""REST routes for the vectorizer service."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from vectorizer.api.dependencies import get_vectorize_service
from vectorizer.domain.models import (
    IngestPackageRequest,
    IngestRequest,
    IngestResponse,
)
from vectorizer.domain.vectorize_service import VectorizeService

router = APIRouter()


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/ingest",
    response_model=IngestResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Vectorize a govinfo collection into pgvector",
)
async def ingest(
    payload: IngestRequest,
    service: Annotated[VectorizeService, Depends(get_vectorize_service)],
) -> IngestResponse:
    return await service.ingest(payload)


@router.post(
    "/ingest/package",
    response_model=IngestResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Vectorize a single govinfo packageId into pgvector",
)
async def ingest_package(
    payload: IngestPackageRequest,
    service: Annotated[VectorizeService, Depends(get_vectorize_service)],
) -> IngestResponse:
    return await service.ingest_package(payload)
