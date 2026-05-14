from __future__ import annotations

from question_api.core.voice_settings import VoiceSettings
from question_api.voice.pipeline import build_nova_sonic_settings, build_transport_params


def test_build_transport_params_enables_bidirectional_audio() -> None:
    params = build_transport_params()

    assert params.audio_in_enabled is True
    assert params.audio_out_enabled is True
    assert params.video_in_enabled is False
    assert params.video_out_enabled is False


def test_build_nova_sonic_settings_includes_grounded_voice_instruction() -> None:
    settings = build_nova_sonic_settings(
        VoiceSettings(
            NOVA_SONIC_MODEL="amazon.nova-2-sonic-v1:0",
            NOVA_SONIC_VOICE="tiffany",
            NOVA_SONIC_ENDPOINTING_SENSITIVITY="HIGH",
            _env_file=None,
        )
    )

    assert settings.model == "amazon.nova-2-sonic-v1:0"
    assert settings.voice == "tiffany"
    assert settings.endpointing_sensitivity == "HIGH"
    assert "answer_question" in settings.system_instruction
    assert "provided context" in settings.system_instruction
