"""In-memory transcript event fan-out for active voice sessions."""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

VoiceTranscriptRole = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class VoiceTranscriptEvent:
    """Transcript event emitted by the voice pipeline."""

    id: int
    session_id: UUID
    role: VoiceTranscriptRole
    transcript: str
    timestamp: str | None = None
    interrupted: bool | None = None

    def to_sse(self) -> str:
        payload: dict[str, Any] = {
            "id": self.id,
            "sessionId": str(self.session_id),
            "role": self.role,
            "transcript": self.transcript,
        }
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        if self.interrupted is not None:
            payload["interrupted"] = self.interrupted

        return f"id: {self.id}\nevent: transcript\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


class VoiceTranscriptBroker:
    """Fan out finalized transcript events to SSE subscribers."""

    def __init__(self, *, history_limit: int = 20) -> None:
        self._history_limit = history_limit
        self._next_id = 1
        self._lock = threading.Lock()
        self._history: dict[UUID, deque[VoiceTranscriptEvent]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._subscribers: dict[UUID, set[asyncio.Queue[VoiceTranscriptEvent]]] = defaultdict(set)

    async def publish(
        self,
        *,
        session_id: UUID,
        role: VoiceTranscriptRole,
        transcript: str,
        timestamp: str | None = None,
        interrupted: bool | None = None,
    ) -> VoiceTranscriptEvent | None:
        text = transcript.strip()
        if not text:
            return None

        with self._lock:
            event = VoiceTranscriptEvent(
                id=self._next_id,
                session_id=session_id,
                role=role,
                transcript=text,
                timestamp=timestamp,
                interrupted=interrupted,
            )
            self._next_id += 1
            self._history[session_id].append(event)
            subscribers = tuple(self._subscribers.get(session_id, ()))

        for queue in subscribers:
            await queue.put(event)

        return event

    async def subscribe(self, session_id: UUID, *, after_id: int | None = None) -> AsyncIterator[VoiceTranscriptEvent]:
        queue: asyncio.Queue[VoiceTranscriptEvent] = asyncio.Queue()
        with self._lock:
            self._subscribers[session_id].add(queue)
            history = self.history(session_id, after_id=after_id)
        try:
            for event in history:
                yield event

            while True:
                event = await queue.get()
                if after_id is None or event.id > after_id:
                    yield event
        finally:
            subscribers = self._subscribers.get(session_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(session_id, None)

    def clear_session(self, session_id: UUID) -> None:
        self._history.pop(session_id, None)

    def history(self, session_id: UUID, *, after_id: int | None = None) -> tuple[VoiceTranscriptEvent, ...]:
        return tuple(
            event
            for event in self._history.get(session_id, ())
            if after_id is None or event.id > after_id
        )


voice_transcript_broker = VoiceTranscriptBroker()
