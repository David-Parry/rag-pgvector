from __future__ import annotations

import uuid

import pytest
from _question_api_fakes import FakeLLM, FakeStore, hit

from question_api.domain.ask_service import AskService
from question_api.domain.models import AskRequest
from rag_core.settings import RetrievalSettings


def _service(store: FakeStore, llm: FakeLLM) -> AskService:
    from langgraph.checkpoint.memory import MemorySaver

    from question_api.domain.ask_graph import compile_ask_graph

    graph = compile_ask_graph(
        store=store,
        llm=llm,
        retrieval=RetrievalSettings(_env_file=None),
        provider_name="anthropic",
        checkpointer=MemorySaver(),
    )
    return AskService(
        graph=graph,
        store=store,
        llm=llm,
        retrieval=RetrievalSettings(_env_file=None),
        provider_name="anthropic",
    )


@pytest.mark.asyncio
async def test_same_session_id_accumulates_messages_and_aca_turns() -> None:
    store = FakeStore(hits=[hit(1, 0.1)])
    llm = FakeLLM(reply="ok")
    service = _service(store, llm)
    sid = uuid.uuid4()

    await service.ask(AskRequest(question="first", session_id=sid))
    await service.ask(AskRequest(question="second", session_id=sid))

    assert len(store.search_calls) == 1
    assert store.search_calls[0]["query"] == "first"

    config = {"configurable": {"thread_id": str(sid)}}
    snap = await service._graph.aget_state(config)
    assert snap is not None
    msgs = snap.values["messages"]
    assert len(msgs) == 4
    turns = snap.values["aca_truth_turns"]
    assert len(turns) == 2
    assert turns[0]["user_message_id"] != turns[1]["user_message_id"]


@pytest.mark.asyncio
async def test_different_session_ids_isolated() -> None:
    store = FakeStore(hits=[hit(1, 0.1)])
    llm = FakeLLM(reply="x")
    service = _service(store, llm)
    a = uuid.uuid4()
    b = uuid.uuid4()

    await service.ask(AskRequest(question="a1", session_id=a))
    await service.ask(AskRequest(question="a2", session_id=a))
    await service.ask(AskRequest(question="b1", session_id=b))

    snap_a = await service._graph.aget_state({"configurable": {"thread_id": str(a)}})
    snap_b = await service._graph.aget_state({"configurable": {"thread_id": str(b)}})
    assert snap_a is not None and snap_b is not None
    assert len(snap_a.values["messages"]) == 4
    assert len(snap_b.values["messages"]) == 2


@pytest.mark.asyncio
async def test_consecutive_duplicate_question_skips_pgvector_and_llm() -> None:
    """Same natural-language question twice in one session reuses the prior answer."""
    store = FakeStore(hits=[hit(1, 0.1)])
    llm = FakeLLM(reply="grounded once")
    service = _service(store, llm)
    sid = uuid.uuid4()
    question = "What is the ACA truth policy?"

    first = await service.ask(AskRequest(question=question, session_id=sid))
    second = await service.ask(
        AskRequest(question=f"  {question.upper()}  ", session_id=sid)
    )

    assert first.answer == "grounded once"
    assert second.answer == "grounded once"
    assert len(store.search_calls) == 1
    assert len(llm.calls) == 1
    assert second.used_context_count == first.used_context_count
    assert first.from_redis_session_cache is False
    assert second.from_redis_session_cache is True
