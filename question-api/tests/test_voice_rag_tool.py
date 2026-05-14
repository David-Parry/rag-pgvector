from __future__ import annotations

import uuid

import pytest

from question_api.domain.models import AskRequest, AskResponse, Citation
from question_api.voice.rag_tool import (
    answer_question_from_transcript,
    build_answer_question_schema,
    build_answer_question_tool_handler,
)


class _RecordingAskService:
    def __init__(self) -> None:
        self.requests: list[AskRequest] = []

    async def ask(self, request: AskRequest) -> AskResponse:
        self.requests.append(request)
        return AskResponse(
            answer="grounded answer",
            citations=[
                Citation(
                    packageId="PKG-1",
                    sourceUrl="https://example.gov/pkg-1",
                    pageNumber=3,
                    score=0.12,
                    snippet="supporting context",
                )
            ],
            usedContextCount=1,
            provider="anthropic",
            fromRedisSessionCache=False,
        )


@pytest.mark.asyncio
async def test_answer_question_from_transcript_uses_final_text_as_ask_question() -> None:
    service = _RecordingAskService()
    session_id = uuid.uuid4()

    result = await answer_question_from_transcript(
        service=service,
        transcript="  What does the bill say about grants?  ",
        session_id=session_id,
        metadata={"collection": "BILLS"},
        top_k=3,
        score_threshold=0.4,
    )

    assert len(service.requests) == 1
    request = service.requests[0]
    assert request.question == "What does the bill say about grants?"
    assert request.session_id == session_id
    assert request.metadata == {"collection": "BILLS"}
    assert request.top_k == 3
    assert request.score_threshold == 0.4
    assert result["answer"] == "grounded answer"
    assert result["usedContextCount"] == 1
    assert result["citations"][0]["packageId"] == "PKG-1"


@pytest.mark.asyncio
async def test_answer_question_from_transcript_rejects_blank_transcripts() -> None:
    service = _RecordingAskService()

    with pytest.raises(ValueError, match="final transcript"):
        await answer_question_from_transcript(
            service=service,
            transcript="   ",
            session_id=uuid.uuid4(),
        )

    assert service.requests == []


class _FakeFunctionParams:
    def __init__(self, arguments: dict[str, object]) -> None:
        self.arguments = arguments
        self.results: list[dict[str, object]] = []

    async def result_callback(self, result: dict[str, object]) -> None:
        self.results.append(result)


@pytest.mark.asyncio
async def test_answer_question_tool_handler_returns_result_to_nova_sonic_callback() -> None:
    service = _RecordingAskService()
    session_id = uuid.uuid4()
    params = _FakeFunctionParams({"question": "What changed?", "metadata": {"collection": "BILLS"}})
    handler = build_answer_question_tool_handler(service=service, session_id=session_id)

    await handler(params)

    assert service.requests[0].question == "What changed?"
    assert service.requests[0].metadata == {"collection": "BILLS"}
    assert params.results == [
        {
            "answer": "grounded answer",
            "citations": [
                {
                    "packageId": "PKG-1",
                    "sourceUrl": "https://example.gov/pkg-1",
                    "pageNumber": 3,
                    "score": 0.12,
                    "snippet": "supporting context",
                }
            ],
            "usedContextCount": 1,
            "provider": "anthropic",
            "fromRedisSessionCache": False,
        }
    ]


@pytest.mark.asyncio
async def test_answer_question_tool_handler_uses_session_defaults() -> None:
    service = _RecordingAskService()
    params = _FakeFunctionParams({"question": "What changed?"})
    handler = build_answer_question_tool_handler(
        service=service,
        session_id=uuid.uuid4(),
        metadata={"collection": "BILLS"},
        top_k=4,
        score_threshold=0.35,
    )

    await handler(params)

    assert service.requests[0].metadata == {"collection": "BILLS"}
    assert service.requests[0].top_k == 4
    assert service.requests[0].score_threshold == 0.35


def test_answer_question_schema_exposes_transcript_question_contract() -> None:
    schema = build_answer_question_schema()

    assert schema.name == "answer_question"
    assert "question" in schema.properties
    assert schema.required == ["question"]
