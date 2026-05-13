"""Orchestrator for the strictly-grounded ask flow via LangGraph + checkpointing."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from langchain_core.messages import AIMessage

from question_api.domain.ask_graph import _msg_content, _msg_role, human_message_for_turn
from question_api.domain.ask_retrieval import filter_chunks_by_threshold
from question_api.domain.models import AskRequest, AskResponse, Citation
from rag_core.ports import LLMPort, RetrievedChunk, VectorStorePort
from rag_core.settings import RetrievalSettings


class AskService:
    """LangGraph-backed retrieve -> threshold -> ground -> generate."""

    def __init__(
        self,
        *,
        graph: Any,
        store: VectorStorePort,
        llm: LLMPort,
        retrieval: RetrievalSettings,
        provider_name: str,
        logger: structlog.stdlib.BoundLogger | None = None,
        session_memory_backend: str = "memory",
        session_memory_endpoint: str | None = None,
    ) -> None:
        self._graph = graph
        self._store = store
        self._llm = llm
        self._retrieval = retrieval
        self._provider_name = provider_name
        self._session_memory_backend = session_memory_backend
        self._session_memory_endpoint = session_memory_endpoint
        self._log = logger or structlog.get_logger(__name__)

    async def ask(self, request: AskRequest) -> AskResponse:
        top_k = request.top_k or self._retrieval.top_k
        threshold = (
            request.score_threshold
            if request.score_threshold is not None
            else self._retrieval.score_threshold
        )
        session = str(request.session_id)
        turn_id = str(uuid.uuid4())
        human = human_message_for_turn(question=request.question.strip(), turn_id=turn_id)

        log = self._log.bind(
            top_k=top_k,
            threshold=threshold,
            provider=self._provider_name,
            session_id=session,
            session_memory_backend=self._session_memory_backend,
            session_memory_endpoint=self._session_memory_endpoint,
        )
        graph_cfg: dict[str, Any] = {
            "thread_id": session,
            "metadata": dict(request.metadata),
            "top_k": top_k,
            "score_threshold": threshold,
        }

        prior_messages = 0
        prior_aca_turns = 0
        precheck_ok = True
        try:
            snap = await self._graph.aget_state({"configurable": graph_cfg})
            if snap and getattr(snap, "values", None):
                prior_messages = len(snap.values.get("messages") or [])
                prior_aca_turns = len(snap.values.get("aca_truth_turns") or [])
        except Exception as exc:  # noqa: BLE001 — visibility only
            precheck_ok = False
            log.warning("ask.checkpoint_precheck_failed", error=str(exc))

        log.info(
            "ask.langgraph_checkpoint_read",
            thread_id=session,
            checkpoint_precheck_ok=precheck_ok,
            prior_message_count=prior_messages,
            prior_aca_truth_turn_count=prior_aca_turns,
            session_memory_serves_context=self._session_memory_backend == "redis",
            note=(
                "LangGraph loads/writes session state via the configured checkpointer "
                "(Redis when session_memory_backend=redis). aget_state reads the latest "
                "checkpoint for thread_id before merging the new user message."
            ),
        )

        final: dict[str, Any] = await self._graph.ainvoke(
            {"messages": [human]},
            config={"configurable": graph_cfg},
        )

        msgs_out = final.get("messages") or []
        if not msgs_out:
            raise RuntimeError("ask graph did not end with an AIMessage")

        last_ai = msgs_out[-1]
        if isinstance(last_ai, AIMessage):
            answer = str(last_ai.content)
        elif _msg_role(last_ai) == "ai":
            answer = _msg_content(last_ai)
        else:
            raise RuntimeError("ask graph did not end with an AIMessage")

        aca_list = final.get("aca_truth_turns") or []
        if not aca_list:
            raise RuntimeError("ask graph missing aca_truth_turns")

        last_aca = aca_list[-1]
        from_redis_session_cache = bool(last_aca.get("from_redis_session_cache"))
        raw_citations = last_aca.get("citations") or []
        citations = [Citation.model_validate(c) for c in raw_citations]
        used_context_count = len(citations)

        log.info(
            "ask.langgraph_checkpoint_write",
            thread_id=session,
            final_message_count=len(msgs_out),
            final_aca_truth_turn_count=len(aca_list),
            last_ai_message_id=getattr(last_ai, "id", None),
            session_memory_serves_context=self._session_memory_backend == "redis",
        )

        return AskResponse(
            answer=answer,
            citations=citations,
            usedContextCount=used_context_count,
            provider=self._provider_name,
            from_redis_session_cache=from_redis_session_cache,
        )

    @staticmethod
    def _apply_threshold(
        hits: Sequence[RetrievedChunk],
        *,
        threshold: float,
    ) -> list[RetrievedChunk]:
        """Cosine *distance* in pgvector: lower = more similar. Drop above-threshold."""
        return filter_chunks_by_threshold(hits, threshold=threshold)
