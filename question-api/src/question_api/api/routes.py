"""REST routes for the question-api service."""

from __future__ import annotations

from typing import Annotated

from botocore.exceptions import NoCredentialsError
from fastapi import APIRouter, Depends, HTTPException, status

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
    try:
        return await service.ask(payload)
    except NoCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Bedrock embedding credentials are not configured. Set AWS auth values "
                "or install the chart with an on-prem embedding provider."
            ),
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The Anthropic answer-generation request timed out.",
        ) from exc
