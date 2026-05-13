"""Domain models for the question-api service (request/response)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Body of ``POST /ask``."""

    question: str = Field(..., min_length=1, max_length=2000)
    session_id: UUID = Field(
        ...,
        alias="sessionId",
        description="Per-tab chat session id (GUID); used as LangGraph thread_id.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata filter applied to the pgvector similarity search (e.g. collection).",
    )
    top_k: int | None = Field(default=None, ge=1, le=50, alias="topK")
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        alias="scoreThreshold",
        description="Override the default cosine-distance threshold (lower = stricter).",
    )

    model_config = {"populate_by_name": True}


class Citation(BaseModel):
    """A single retrieved chunk that contributed to the answer."""

    package_id: str = Field(alias="packageId")
    source_url: str = Field(alias="sourceUrl")
    page_number: int | None = Field(default=None, alias="pageNumber")
    score: float
    snippet: str

    model_config = {"populate_by_name": True}


class AskResponse(BaseModel):
    """Body of the ``POST /ask`` response."""

    answer: str
    citations: list[Citation]
    used_context_count: int = Field(alias="usedContextCount")
    provider: str
    from_redis_session_cache: bool = Field(
        default=False,
        alias="fromRedisSessionCache",
        description=(
            "True when this answer reused the prior turn from LangGraph session checkpoint "
            "(Redis in production) without a new pgvector similarity search or LLM call "
            "(consecutive duplicate user question)."
        ),
    )

    model_config = {"populate_by_name": True}
