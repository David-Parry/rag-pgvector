"""Tool bridge from Pipecat finalized transcripts to the existing RAG service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from question_api.domain.ask_service import AskService
from question_api.domain.models import AskRequest


class FunctionCallParamsLike(Protocol):
    """Small subset of Pipecat ``FunctionCallParams`` used by the RAG tool."""

    arguments: dict[str, Any]

    def result_callback(self, result: dict[str, Any]) -> Awaitable[None]: ...


def build_answer_question_schema() -> Any:
    """Build the Pipecat tool schema for grounded RAG question answering."""

    from pipecat.adapters.schemas.function_schema import FunctionSchema

    return FunctionSchema(
        name="answer_question",
        description=(
            "Answer a finalized user voice transcript using the existing grounded RAG "
            "question-answering service."
        ),
        properties={
            "question": {
                "type": "string",
                "description": "The complete finalized user transcript to answer.",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata filter for pgvector retrieval.",
            },
            "topK": {
                "type": "integer",
                "description": "Optional retrieval top-k override.",
            },
            "scoreThreshold": {
                "type": "number",
                "description": "Optional cosine-distance threshold override.",
            },
        },
        required=["question"],
    )


async def answer_question_from_transcript(
    *,
    service: AskService,
    transcript: str,
    session_id: UUID,
    metadata: dict[str, Any] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> dict[str, Any]:
    """Use a finalized voice transcript as the canonical RAG question."""

    question = transcript.strip()
    if not question:
        raise ValueError("A final transcript is required before querying RAG.")

    response = await service.ask(
        AskRequest(
            question=question,
            session_id=session_id,
            metadata=dict(metadata or {}),
            top_k=top_k,
            score_threshold=score_threshold,
        )
    )
    return response.model_dump(mode="json", by_alias=True)


def build_answer_question_tool_handler(
    *,
    service: AskService,
    session_id: UUID,
    metadata: dict[str, Any] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> Callable[[FunctionCallParamsLike], Awaitable[None]]:
    """Build a Pipecat function handler that delegates finalized transcript text to RAG."""

    async def handler(params: FunctionCallParamsLike) -> None:
        transcript = _transcript_from_arguments(params.arguments)
        metadata_arg = params.arguments.get("metadata")
        top_k_arg = params.arguments.get("topK")
        score_threshold_arg = params.arguments.get("scoreThreshold")
        result = await answer_question_from_transcript(
            service=service,
            transcript=transcript,
            session_id=session_id,
            metadata=metadata_arg if isinstance(metadata_arg, dict) else metadata,
            top_k=top_k_arg if isinstance(top_k_arg, int) else top_k,
            score_threshold=(
                float(score_threshold_arg)
                if isinstance(score_threshold_arg, (int, float))
                else score_threshold
            ),
        )
        await params.result_callback(result)

    return handler


def _transcript_from_arguments(arguments: dict[str, Any]) -> str:
    raw = arguments.get("question")
    if raw is None:
        raw = arguments.get("transcript")
    return str(raw or "")
