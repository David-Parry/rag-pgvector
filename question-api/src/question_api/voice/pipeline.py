"""Pipecat pipeline assembly for the in-process Nova Sonic voice bot."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from pydantic import SecretStr

from question_api.core.composition import Container
from question_api.core.voice_settings import VoiceSettings
from question_api.voice.rag_tool import (
    build_answer_question_schema,
    build_answer_question_tool_handler,
)
from question_api.voice.transcripts import voice_transcript_broker


def build_transport_params() -> Any:
    """Create the Small WebRTC transport parameters used by question-api voice."""

    from pipecat.transports.base_transport import TransportParams

    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_in_enabled=False,
        video_out_enabled=False,
    )


def build_nova_sonic_settings(settings: VoiceSettings) -> Any:
    """Create Nova Sonic runtime settings with the grounded RAG tool instruction."""

    from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService

    return AWSNovaSonicLLMService.Settings(
        model=settings.model,
        voice=settings.voice,
        endpointing_sensitivity=settings.endpointing_sensitivity,
        system_instruction=_voice_system_instruction(settings),
    )


async def run_voice_bot(
    *,
    webrtc_connection: Any,
    container: Container,
    session_id: UUID,
    metadata: dict[str, Any] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> None:
    """Run one Pipecat voice bot connected to an accepted Small WebRTC session."""

    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.frames.frames import LLMRunFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        AssistantTurnStoppedMessage,
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
        UserTurnStoppedMessage,
    )
    from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

    log = structlog.get_logger("question_api.voice")
    voice_settings = container.settings.voice
    transport = SmallWebRTCTransport(
        params=build_transport_params(),
        webrtc_connection=webrtc_connection,
    )
    tools = ToolsSchema(standard_tools=[build_answer_question_schema()])
    llm = AWSNovaSonicLLMService(
        secret_access_key=_secret_value(voice_settings.secret_access_key),
        access_key_id=_secret_value(voice_settings.access_key_id),
        session_token=_secret_value_or_none(voice_settings.session_token),
        region=voice_settings.region,
        settings=build_nova_sonic_settings(voice_settings),
        tools=tools,
    )
    handler = build_answer_question_tool_handler(
        service=container.service,
        session_id=session_id,
        metadata=metadata,
        top_k=top_k,
        score_threshold=score_threshold,
    )
    llm.register_function(
        "answer_question",
        handler,
        cancel_on_interruption=False,
    )

    context = LLMContext(tools=tools)
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=ExternalUserTurnStrategies(),
        ),
    )
    user_aggregator = aggregators.user()
    assistant_aggregator = aggregators.assistant()
    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        conversation_id=str(session_id),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport: Any, _connection: Any) -> None:
        # Nova Sonic only finishes its bidirectional-stream setup (sending
        # promptStart, system instruction, and audioInputContent start) after
        # receiving an LLMContextFrame. Without this kick, the service stays in
        # pre-setup state and silently drops every incoming audio frame in
        # _send_user_audio_event because _audio_input_started is False.
        await task.queue_frame(LLMRunFrame())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport: Any, _connection: Any) -> None:
        log.info("voice.client_disconnected", session_id=str(session_id))
        await task.cancel()

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(
        _aggregator: Any,
        _strategy: Any,
        message: UserTurnStoppedMessage,
    ) -> None:
        await voice_transcript_broker.publish(
            session_id=session_id,
            role="user",
            transcript=message.content,
            timestamp=str(message.timestamp) if message.timestamp is not None else None,
        )
        log.info(
            "voice.user_transcript_finalized",
            session_id=str(session_id),
            transcript=message.content,
            timestamp=message.timestamp,
            metadata=dict(metadata or {}),
            top_k=top_k,
            score_threshold=score_threshold,
        )

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(
        _aggregator: Any,
        message: AssistantTurnStoppedMessage,
    ) -> None:
        await voice_transcript_broker.publish(
            session_id=session_id,
            role="assistant",
            transcript=message.content,
            timestamp=str(message.timestamp) if message.timestamp is not None else None,
            interrupted=message.interrupted,
        )
        log.info(
            "voice.assistant_transcript_finalized",
            session_id=str(session_id),
            transcript=message.content,
            interrupted=message.interrupted,
            timestamp=message.timestamp,
        )

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


def _voice_system_instruction(settings: VoiceSettings) -> str:
    return (
        settings.system_instruction.strip()
        + "\n\nFor every knowledge question, call the answer_question tool with the "
        "complete finalized user transcript. Speak only the grounded answer returned "
        "by the tool. If the tool returns \"I don't know based on the provided context.\", "
        "say that exactly."
    )


def _secret_value(value: SecretStr | None) -> str:
    return value.get_secret_value() if value is not None else ""


def _secret_value_or_none(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None
