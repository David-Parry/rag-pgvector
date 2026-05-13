from __future__ import annotations

import uuid

import pytest
from _question_api_fakes import FakeLLM, FakeStore, hit

from question_api.domain.ask_service import AskService
from question_api.domain.models import AskRequest
from rag_core.settings import RetrievalSettings


def _retrieval(top_k: int = 3, threshold: float = 0.5) -> RetrievalSettings:
    return RetrievalSettings(
        RETRIEVAL_TOP_K=top_k,
        RETRIEVAL_SCORE_THRESHOLD=threshold,
        _env_file=None,
    )


def _service(store: FakeStore, llm: FakeLLM, retrieval: RetrievalSettings | None = None) -> AskService:
    from langgraph.checkpoint.memory import MemorySaver

    from question_api.domain.ask_graph import compile_ask_graph

    retrieval = retrieval or _retrieval()
    graph = compile_ask_graph(
        store=store,
        llm=llm,
        retrieval=retrieval,
        provider_name="anthropic",
        checkpointer=MemorySaver(),
    )
    return AskService(
        graph=graph,
        store=store,
        llm=llm,
        retrieval=retrieval,
        provider_name="anthropic",
    )


@pytest.mark.asyncio
async def test_ask_returns_grounded_answer_with_citations() -> None:
    store = FakeStore(hits=[hit(1, 0.1), hit(2, 0.2)])
    llm = FakeLLM(reply="alpha")
    service = _service(store, llm)

    response = await service.ask(
        AskRequest(question="What is alpha?", session_id=uuid.uuid4())
    )

    assert response.answer == "alpha"
    assert response.used_context_count == 2
    assert response.provider == "anthropic"
    assert response.from_redis_session_cache is False
    assert {c.package_id for c in response.citations} == {"PKG-1"}
    assert all(c.snippet for c in response.citations)


@pytest.mark.asyncio
async def test_ask_drops_hits_above_threshold() -> None:
    store = FakeStore(hits=[hit(1, 0.1), hit(2, 0.9), hit(3, 0.4)])
    service = _service(
        store,
        FakeLLM(reply="answer"),
        retrieval=_retrieval(threshold=0.5),
    )

    response = await service.ask(AskRequest(question="?", session_id=uuid.uuid4()))

    assert response.used_context_count == 2


@pytest.mark.asyncio
async def test_ask_returns_no_context_message_when_all_hits_filtered() -> None:
    store = FakeStore(hits=[hit(1, 0.99)])
    llm = FakeLLM(reply="should not be called")
    service = _service(
        store,
        llm,
        retrieval=_retrieval(threshold=0.2),
    )

    response = await service.ask(AskRequest(question="?", session_id=uuid.uuid4()))

    assert response.answer == "I don't know based on the provided context."
    assert response.used_context_count == 0
    assert llm.calls == []


@pytest.mark.asyncio
async def test_ask_propagates_metadata_filter_and_top_k_overrides() -> None:
    store = FakeStore(hits=[hit(1, 0.1)])
    service = _service(store, FakeLLM(reply="ok"), retrieval=_retrieval(top_k=5, threshold=0.5))

    await service.ask(
        AskRequest(
            question="?",
            session_id=uuid.uuid4(),
            metadata={"collection": "BILLS"},
            topK=2,
            scoreThreshold=0.3,
        )
    )

    call = store.search_calls[0]
    assert call["k"] == 2
    assert call["filter"] == {"collection": "BILLS"}
