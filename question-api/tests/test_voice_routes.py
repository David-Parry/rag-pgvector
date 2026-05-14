from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from question_api.core.voice_settings import VoiceSettings
from question_api.voice.routes import router
from question_api.voice.transcripts import voice_transcript_broker


class _Container:
    def __init__(self, *, voice_enabled: bool = True) -> None:
        self.settings = type(
            "Settings",
            (),
            {"voice": VoiceSettings(VOICE_ENABLED=voice_enabled, _env_file=None)},
        )()
        self.service = object()


class _FakeSmallWebRTCHandler:
    def __init__(self) -> None:
        self.patch_requests = []

    async def handle_web_request(self, *, request, webrtc_connection_callback):
        await webrtc_connection_callback("connection")
        return {"sdp": "answer-sdp", "type": "answer"}

    async def handle_patch_request(self, request):
        self.patch_requests.append(request)


def _app(*, voice_enabled: bool = True) -> FastAPI:
    app = FastAPI()
    app.state.container = _Container(voice_enabled=voice_enabled)
    app.include_router(router)
    return app


def test_voice_start_returns_session_id_and_optional_ice_config() -> None:
    client = TestClient(_app())

    response = client.post("/voice/start", json={"enableDefaultIceServers": True})

    assert response.status_code == 200
    body = response.json()
    UUID(body["sessionId"])
    assert body["iceConfig"] == {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}


def test_voice_start_returns_404_when_voice_disabled() -> None:
    client = TestClient(_app(voice_enabled=False))

    response = client.post("/voice/start", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "Voice endpoint is disabled"


def test_voice_offer_starts_bot_with_container_and_session(monkeypatch) -> None:
    import question_api.voice.routes as voice_routes

    calls = []

    async def fake_run_voice_bot(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(voice_routes, "_small_webrtc_handler", _FakeSmallWebRTCHandler())
    monkeypatch.setattr(voice_routes, "run_voice_bot", fake_run_voice_bot)
    client = TestClient(_app())
    start = client.post("/voice/start", json={"metadata": {"collection": "BILLS"}}).json()

    response = client.post(
        "/voice/api/offer",
        json={
            "sdp": "offer-sdp",
            "type": "offer",
            "request_data": {"sessionId": start["sessionId"]},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"sdp": "answer-sdp", "type": "answer"}
    assert calls[0]["webrtc_connection"] == "connection"
    assert calls[0]["metadata"] == {"collection": "BILLS"}
    assert str(calls[0]["session_id"]) == start["sessionId"]


def test_voice_patch_delegates_ice_candidates(monkeypatch) -> None:
    import question_api.voice.routes as voice_routes

    handler = _FakeSmallWebRTCHandler()
    monkeypatch.setattr(voice_routes, "_small_webrtc_handler", handler)
    client = TestClient(_app())

    response = client.patch(
        "/voice/api/offer",
        json={
            "pc_id": "pc-1",
            "candidates": [
                {
                    "candidate": "candidate:1",
                    "sdp_mid": "0",
                    "sdp_mline_index": 0,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert len(handler.patch_requests) == 1


def test_voice_transcript_stream_replays_finalized_events() -> None:
    client = TestClient(_app())
    start = client.post("/voice/start", json={}).json()

    import asyncio

    asyncio.run(
        voice_transcript_broker.publish(
            session_id=UUID(start["sessionId"]),
            role="user",
            transcript="What is in the bill?",
            timestamp="2026-05-14T21:05:00Z",
        )
    )

    with client.stream("GET", f"/voice/transcripts/{start['sessionId']}?replayOnly=true") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        lines = []
        for line in response.iter_lines():
            lines.append(line)
            if line == "":
                break

    assert "event: transcript" in lines
    assert any('"role":"user"' in line for line in lines)
    assert any('"transcript":"What is in the bill?"' in line for line in lines)
