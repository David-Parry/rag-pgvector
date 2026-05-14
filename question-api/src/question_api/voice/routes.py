"""FastAPI routes for Pipecat Small WebRTC voice sessions."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from question_api.voice.pipeline import run_voice_bot
from question_api.voice.transcripts import voice_transcript_broker

router = APIRouter(prefix="/voice", tags=["voice"])
_small_webrtc_handler = SmallWebRTCRequestHandler()


class IceServer(TypedDict, total=False):
    urls: list[str]


class IceConfig(TypedDict):
    iceServers: list[IceServer]


@dataclass(slots=True)
class VoiceSession:
    session_id: UUID
    metadata: dict[str, Any] = field(default_factory=dict)
    top_k: int | None = None
    score_threshold: float | None = None


_active_sessions: dict[str, VoiceSession] = {}


@router.post("/start", status_code=status.HTTP_200_OK)
async def voice_start(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a voice session id for the browser WebRTC client."""

    container = _container_from_request(request)
    _ensure_voice_enabled(container)

    body = payload or {}
    session_id = _session_id_from_payload(body)
    session = VoiceSession(
        session_id=session_id,
        metadata=_metadata_from_payload(body),
        top_k=_int_or_none(body.get("topK")),
        score_threshold=_float_or_none(body.get("scoreThreshold")),
    )
    _active_sessions[str(session_id)] = session
    result: dict[str, Any] = {"sessionId": str(session_id)}
    if body.get("enableDefaultIceServers"):
        result["iceConfig"] = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    return result


@router.post("/api/offer", status_code=status.HTTP_200_OK)
async def voice_offer(
    request_payload: SmallWebRTCRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict[str, str] | None:
    """Handle a Small WebRTC offer and start the Pipecat bot in the background."""

    container = _container_from_request(request)
    _ensure_voice_enabled(container)
    session = _session_from_offer(request_payload)

    async def webrtc_connection_callback(connection: Any) -> None:
        background_tasks.add_task(
            run_voice_bot,
            webrtc_connection=connection,
            container=container,
            session_id=session.session_id,
            metadata=session.metadata,
            top_k=session.top_k,
            score_threshold=session.score_threshold,
        )

    return await _small_webrtc_handler.handle_web_request(
        request=request_payload,
        webrtc_connection_callback=webrtc_connection_callback,
    )


@router.patch("/api/offer", status_code=status.HTTP_200_OK)
async def voice_ice_candidate(request_payload: SmallWebRTCPatchRequest) -> dict[str, str]:
    """Handle Small WebRTC ICE candidate patches."""

    await _small_webrtc_handler.handle_patch_request(request_payload)
    return {"status": "success"}


@router.get("/transcripts/{session_id}", status_code=status.HTTP_200_OK)
async def voice_transcripts(
    session_id: UUID,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    replay_only: bool = Query(default=False, alias="replayOnly"),
) -> StreamingResponse:
    """Stream finalized voice transcript events for an active browser session."""

    container = _container_from_request(request)
    _ensure_voice_enabled(container)
    after_id = _event_id_or_none(last_event_id)

    async def events() -> AsyncIterator[str]:
        if replay_only:
            for event in voice_transcript_broker.history(session_id, after_id=after_id):
                yield event.to_sse()
            return

        async for event in voice_transcript_broker.subscribe(session_id, after_id=after_id):
            if await request.is_disconnected():
                break
            yield event.to_sse()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def close_voice_sessions() -> None:
    """Close Small WebRTC handler resources during app shutdown."""

    await cast(Awaitable[None], _small_webrtc_handler.close())  # type: ignore[no-untyped-call]


def _container_from_request(request: Request) -> Any:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="question-api container is not initialized",
        )
    return container


def _ensure_voice_enabled(container: Any) -> None:
    settings = getattr(getattr(container, "settings", None), "voice", None)
    if settings is not None and not bool(getattr(settings, "enabled", False)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice endpoint is disabled",
        )


def _session_from_offer(request_payload: SmallWebRTCRequest) -> VoiceSession:
    data = request_payload.request_data if isinstance(request_payload.request_data, dict) else {}
    raw_session_id = data.get("sessionId") or data.get("session_id")
    if raw_session_id:
        session = _active_sessions.get(str(raw_session_id))
        if session is not None:
            return session
        try:
            session_id = UUID(str(raw_session_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request_data.sessionId must be a UUID",
            ) from exc
    else:
        session_id = uuid.uuid4()

    session = VoiceSession(
        session_id=session_id,
        metadata=_metadata_from_payload(data),
        top_k=_int_or_none(data.get("topK")),
        score_threshold=_float_or_none(data.get("scoreThreshold")),
    )
    _active_sessions[str(session_id)] = session
    return session


def _session_id_from_payload(payload: dict[str, Any]) -> UUID:
    raw = payload.get("sessionId") or payload.get("session_id")
    if raw is None:
        return uuid.uuid4()
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sessionId must be a UUID",
        ) from exc


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata must be an object",
        )
    return dict(metadata)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _float_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _event_id_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        event_id = int(value)
    except ValueError:
        return None
    return event_id if event_id >= 0 else None
