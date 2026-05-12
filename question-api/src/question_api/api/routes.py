"""REST routes for the question-api service."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from question_api.api.dependencies import get_ask_service
from question_api.domain.ask_service import AskService
from question_api.domain.models import AskRequest, AskResponse

router = APIRouter()


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/ask",
    response_model=AskResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Answer a question grounded in pgvector context",
)
async def ask(
    payload: AskRequest,
    service: Annotated[AskService, Depends(get_ask_service)],
) -> AskResponse:
    return await service.ask(payload)
