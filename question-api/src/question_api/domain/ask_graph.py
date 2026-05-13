"""LangGraph state machine for one grounded Q/A turn per ``/ask`` invocation."""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, NotRequired, TypedDict

import structlog
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from question_api.domain.ask_retrieval import chunks_to_citations, filter_chunks_by_threshold
from question_api.domain.models import Citation
from rag_core.ports import LLMPort, RetrievedChunk, VectorStorePort
from rag_core.prompts import SYSTEM_PROMPT_QA, build_user_prompt
from rag_core.settings import RetrievalSettings

_INSUFFICIENT_CONTEXT_REPLY = "I don't know based on the provided context."


def _merge_session_vector_chunks(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the first non-empty write; later turns omit this key so state is unchanged."""
    if existing:
        return existing
    return list(new)


def _serialize_retrieved_chunk(c: RetrievedChunk) -> dict[str, Any]:
    return {"id": c.id, "text": c.text, "metadata": dict(c.metadata), "score": float(c.score)}


def _deserialize_retrieved_chunk(d: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        id=str(d["id"]),
        text=str(d["text"]),
        metadata=dict(d.get("metadata") or {}),
        score=float(d["score"]),
    )


def _chunks_from_session_state(raw: Any) -> list[RetrievedChunk]:
    if not isinstance(raw, list):
        return []
    out: list[RetrievedChunk] = []
    for item in raw:
        if isinstance(item, dict) and "id" in item and "text" in item:
            out.append(_deserialize_retrieved_chunk(item))
    return out


def _first_human_question_in_session(msgs: list[Any]) -> str:
    """Vector query for the session: always the first user question in this thread."""
    for m in msgs:
        if _msg_role(m) == "human":
            return _msg_content(m)
    raise ValueError("ask graph expects at least one human message in session")


def _format_prior_conversation(msgs: list[Any]) -> str:
    """Human-readable transcript for PRIOR_CONVERSATION (same session, before current turn)."""
    lines: list[str] = []
    for m in msgs:
        role = _msg_role(m)
        if role == "human":
            lines.append(f"User: {_msg_content(m)}")
        elif role == "ai":
            lines.append(f"Assistant: {_msg_content(m)}")
    return "\n".join(lines).strip()


def _normalize_question_text(text: str) -> str:
    """Collapse whitespace for stable duplicate detection."""
    return " ".join(str(text).split()).strip().lower()


def _normalize_lc_type(type_value: str | None) -> str | None:
    """Map LangChain / serde type strings to ``human`` or ``ai``."""
    if type_value is None:
        return None
    tl = str(type_value).strip().lower()
    if tl in ("human", "humanmessage"):
        return "human"
    if tl in ("ai", "aimessage", "assistant"):
        return "ai"
    return tl


def _lc_constructor_kwargs(msg: dict[str, Any]) -> dict[str, Any] | None:
    """LangChain JsonPlus / Redis checkpoints often wrap messages in this envelope."""
    if msg.get("lc") == 1 and str(msg.get("type", "")).lower() == "constructor":
        raw = msg.get("kwargs")
        return raw if isinstance(raw, dict) else None
    return None


def _role_from_lc_id_list(ids: Any) -> str | None:
    if not isinstance(ids, list):
        return None
    for segment in reversed(ids):
        sl = str(segment).lower()
        if sl.endswith("humanmessage") or sl == "human":
            return "human"
        if sl.endswith("aimessage") or sl == "ai":
            return "ai"
    return None


def _msg_role(msg: Any) -> str | None:
    """Checkpoint serde may restore chat rows as dicts; use role, not only isinstance."""
    if isinstance(msg, BaseMessage):
        return _normalize_lc_type(msg.type)
    if isinstance(msg, dict):
        ctor = _lc_constructor_kwargs(msg)
        if ctor is not None:
            from_id = _role_from_lc_id_list(msg.get("id"))
            if from_id is not None:
                return from_id
            inner = ctor.get("type")
            if inner is not None:
                normalized = _normalize_lc_type(str(inner))
                if normalized in ("human", "ai"):
                    return normalized
        t = msg.get("type")
        if str(t).lower() == "constructor":
            return None
        return _normalize_lc_type(str(t) if t is not None else None)
    return None


def _msg_content(msg: Any) -> str:
    if isinstance(msg, BaseMessage):
        return str(msg.content).strip()
    if isinstance(msg, dict):
        ctor = _lc_constructor_kwargs(msg)
        if ctor is not None:
            c = ctor.get("content")
            if isinstance(c, str):
                return c.strip()
            if c is not None:
                return str(c).strip()
            return ""
        c = msg.get("content")
        return str(c).strip() if c is not None else ""
    c = getattr(msg, "content", None)
    return str(c).strip() if c is not None else ""


def _turn_id_from_message(msg: Any) -> str | None:
    if isinstance(msg, BaseMessage):
        raw = (msg.additional_kwargs or {}).get("turn_id")
        return raw if isinstance(raw, str) else None
    if isinstance(msg, dict):
        ctor = _lc_constructor_kwargs(msg)
        if ctor is not None:
            raw = (ctor.get("additional_kwargs") or {}).get("turn_id")
            return raw if isinstance(raw, str) else None
        raw = (msg.get("additional_kwargs") or {}).get("turn_id")
        return raw if isinstance(raw, str) else None
    raw = (getattr(msg, "additional_kwargs", None) or {}).get("turn_id")
    return raw if isinstance(raw, str) else None


class AcaTruthTurn(TypedDict):
    """One turn's ACA (retrieval) snapshot, joined to chat via ``turn_id`` / message ids."""

    turn_id: str
    user_message_id: str
    assistant_message_id: str
    citations: list[dict[str, Any]]
    question_text: NotRequired[str]
    answer_text: NotRequired[str]
    from_redis_session_cache: NotRequired[bool]


class AskGraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    aca_truth_turns: Annotated[list[AcaTruthTurn], operator.add]
    session_vector_chunks: Annotated[list[dict[str, Any]], _merge_session_vector_chunks]
    session_vector_search_done: Annotated[bool, operator.or_]


def compile_ask_graph(
    *,
    store: VectorStorePort,
    llm: LLMPort,
    retrieval: RetrievalSettings,
    provider_name: str,
    checkpointer: BaseCheckpointSaver,
    logger: structlog.stdlib.BoundLogger | None = None,
    session_memory_backend: str = "memory",
    session_memory_endpoint: str | None = None,
):
    """Compile the single-node ask graph with the given checkpointer (Redis or Memory)."""
    base = logger or structlog.get_logger(__name__)
    log = base.bind(
        session_memory_backend=session_memory_backend,
        session_memory_endpoint=session_memory_endpoint,
    )

    async def rag_node(state: AskGraphState, config: RunnableConfig) -> dict[str, Any]:
        cfg = config.get("configurable") or {}
        metadata = cfg.get("metadata") or {}
        top_k = cfg.get("top_k", retrieval.top_k)
        threshold = cfg.get("score_threshold", retrieval.score_threshold)

        msgs = state["messages"]
        if not msgs or _msg_role(msgs[-1]) != "human":
            raise ValueError("ask graph expects the merged state to end with a human message")

        log.info(
            "ask_graph.session_messages_for_context",
            merged_message_count=len(msgs),
            merged_aca_truth_turn_count=len(state.get("aca_truth_turns") or []),
            thread_id=cfg.get("thread_id"),
            note=(
                "Message list includes prior turns loaded from the LangGraph checkpointer "
                "(Redis in production) merged with this request's HumanMessage."
            ),
        )

        hm = msgs[-1]
        question = _msg_content(hm)
        raw_turn = _turn_id_from_message(hm)
        turn_id = raw_turn if raw_turn else str(uuid.uuid4())
        if isinstance(hm, dict):
            uid = hm.get("id")
            user_mid = str(uid) if isinstance(uid, str) and uid else f"user-{turn_id}"
        else:
            user_mid = str(hm.id) if getattr(hm, "id", None) else f"user-{turn_id}"
        assistant_mid = f"assistant-{turn_id}"

        prior_turns = state.get("aca_truth_turns") or []
        if (
            len(msgs) >= 3
            and _msg_role(msgs[-3]) == "human"
            and _msg_role(msgs[-2]) == "ai"
            and _msg_role(msgs[-1]) == "human"
        ):
            prev_q = _msg_content(msgs[-3])
            if _normalize_question_text(prev_q) == _normalize_question_text(question):
                prev_ai = msgs[-2]
                prior_aca = prior_turns[-1] if prior_turns else None
                citations_raw: list[dict[str, Any]] = (
                    list(prior_aca.get("citations") or []) if prior_aca else []
                )
                answer_text = _msg_content(prev_ai)
                log.info(
                    "ask_graph.duplicate_consecutive_question",
                    thread_id=cfg.get("thread_id"),
                    turn_id=turn_id,
                    skip_pgvector_similarity_search=True,
                    skip_llm_generate=True,
                    note=(
                        "Checkpoint store (e.g. Redis) still receives this graph step; "
                        "vector store and LLM are not called for this duplicate."
                    ),
                )
                aca_dup: AcaTruthTurn = {
                    "turn_id": turn_id,
                    "user_message_id": user_mid,
                    "assistant_message_id": assistant_mid,
                    "citations": citations_raw,
                    "question_text": question,
                    "answer_text": answer_text,
                    "from_redis_session_cache": True,
                }
                return {
                    "messages": [
                        AIMessage(
                            content=answer_text,
                            id=assistant_mid,
                            additional_kwargs={
                                "turn_id": turn_id,
                                "from_redis_session_cache": True,
                            },
                        )
                    ],
                    "aca_truth_turns": [aca_dup],
                }

        vector_query = _first_human_question_in_session(msgs)
        session_done = bool(state.get("session_vector_search_done"))
        prior_transcript = _format_prior_conversation(msgs[:-1])

        if session_done:
            kept = _chunks_from_session_state(state.get("session_vector_chunks") or [])
            log.info(
                "ask_graph.vector_skipped_session_retrieval",
                thread_id=cfg.get("thread_id"),
                turn_id=turn_id,
                chunk_count=len(kept),
                vector_query_was_first_question_preview=vector_query[:200],
                note="One similarity_search per session; reusing chunks from the first question.",
            )
        else:
            log.info(
                "ask_graph.calling_vector",
                message="[Calling Vector]",
                similarity_query_preview=vector_query[:200],
                top_k=int(top_k),
                score_threshold=float(threshold),
                thread_id=cfg.get("thread_id"),
                turn_id=turn_id,
            )
            hits = await store.similarity_search(
                vector_query,
                k=int(top_k),
                metadata_filter=metadata or None,
            )
            kept = filter_chunks_by_threshold(hits, threshold=float(threshold))
            log.info("ask_graph.retrieved", returned=len(hits), kept=len(kept))

        session_update: dict[str, Any] = {}
        if not session_done:
            session_update = {
                "session_vector_search_done": True,
                "session_vector_chunks": [_serialize_retrieved_chunk(c) for c in kept],
            }

        if not kept:
            aca = _aca_turn(
                turn_id=turn_id,
                user_message_id=user_mid,
                assistant_message_id=assistant_mid,
                citations=[],
                question_text=question,
                answer_text=_INSUFFICIENT_CONTEXT_REPLY,
                from_redis_session_cache=False,
            )
            return {
                "messages": [
                    AIMessage(
                        content=_INSUFFICIENT_CONTEXT_REPLY,
                        id=assistant_mid,
                        additional_kwargs={"turn_id": turn_id},
                    )
                ],
                "aca_truth_turns": [aca],
                **session_update,
            }

        user_prompt = build_user_prompt(
            question,
            kept,
            prior_conversation=prior_transcript or None,
        )
        answer = await llm.generate(SYSTEM_PROMPT_QA, user_prompt)
        citations = chunks_to_citations(kept)
        aca = _aca_turn(
            turn_id=turn_id,
            user_message_id=user_mid,
            assistant_message_id=assistant_mid,
            citations=citations,
            question_text=question,
            answer_text=answer,
            from_redis_session_cache=False,
        )
        return {
            "messages": [
                AIMessage(
                    content=answer,
                    id=assistant_mid,
                    additional_kwargs={"turn_id": turn_id},
                )
            ],
            "aca_truth_turns": [aca],
            **session_update,
        }

    builder: StateGraph[AskGraphState] = StateGraph(AskGraphState)
    builder.add_node("rag", rag_node)
    builder.add_edge(START, "rag")
    builder.add_edge("rag", END)
    return builder.compile(checkpointer=checkpointer)


def _aca_turn(
    *,
    turn_id: str,
    user_message_id: str,
    assistant_message_id: str,
    citations: list[Citation],
    question_text: str,
    answer_text: str,
    from_redis_session_cache: bool = False,
) -> AcaTruthTurn:
    serialized = [c.model_dump(mode="json", by_alias=True) for c in citations]
    return {
        "turn_id": turn_id,
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
        "citations": serialized,
        "question_text": question_text,
        "answer_text": answer_text,
        "from_redis_session_cache": from_redis_session_cache,
    }


def human_message_for_turn(*, question: str, turn_id: str) -> HumanMessage:
    """Build the inbound user message for this ``/ask`` (stable ids for ACA linkage)."""
    user_mid = f"user-{turn_id}"
    return HumanMessage(
        content=question,
        id=user_mid,
        additional_kwargs={"turn_id": turn_id},
    )
