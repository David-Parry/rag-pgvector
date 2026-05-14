from __future__ import annotations

from question_api.core.settings import QuestionApiSettings
from question_api.core.voice_settings import VoiceSettings


def test_voice_settings_defaults_to_disabled_nova_sonic() -> None:
    settings = VoiceSettings(_env_file=None)

    assert settings.enabled is False
    assert settings.model == "amazon.nova-2-sonic-v1:0"
    assert settings.voice == "matthew"
    assert settings.endpointing_sensitivity == "MEDIUM"


def test_voice_settings_prefers_nova_sonic_specific_environment(monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0")
    monkeypatch.setenv("SONIC_AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/NovaSonic")
    monkeypatch.setenv("SONIC_AWS_ACCESS_KEY_ID", "sonic-access-key")
    monkeypatch.setenv("SONIC_AWS_SECRET_ACCESS_KEY", "sonic-secret-key")
    monkeypatch.setenv("SONIC_AWS_SESSION_TOKEN", "sonic-session-token")
    monkeypatch.setenv("SONIC_AWS_CREDENTIAL_EXPIRATION", "2026-05-14T20:00:00+00:00")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "embedding-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "embedding-secret-key")

    settings = VoiceSettings(_env_file=None)

    assert settings.model == "amazon.nova-sonic-v1:0"
    assert settings.role_arn == "arn:aws:iam::123456789012:role/NovaSonic"
    assert settings.access_key_id is not None
    assert settings.secret_access_key is not None
    assert settings.session_token is not None
    assert settings.access_key_id.get_secret_value() == "sonic-access-key"
    assert settings.secret_access_key.get_secret_value() == "sonic-secret-key"
    assert settings.session_token.get_secret_value() == "sonic-session-token"
    assert settings.credential_expiration == "2026-05-14T20:00:00+00:00"


def test_question_api_settings_loads_voice_settings() -> None:
    settings = QuestionApiSettings.load()

    assert isinstance(settings.voice, VoiceSettings)
