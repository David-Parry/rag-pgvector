"""Settings for the question-api Pipecat / Nova Sonic voice path."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    """Environment-driven settings for the optional realtime voice endpoint."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = Field(default=False, alias="VOICE_ENABLED")
    model: str = Field(
        default="amazon.nova-2-sonic-v1:0",
        validation_alias=AliasChoices("BEDROCK_NOVA_SONIC_MODEL_ID", "NOVA_SONIC_MODEL"),
    )
    voice: str = Field(default="matthew", alias="NOVA_SONIC_VOICE")
    endpointing_sensitivity: Literal["LOW", "MEDIUM", "HIGH"] | None = Field(
        default="MEDIUM",
        alias="NOVA_SONIC_ENDPOINTING_SENSITIVITY",
    )
    region: str = Field(default="us-east-1", alias="AWS_REGION")
    role_arn: str | None = Field(default=None, alias="SONIC_AWS_ROLE_ARN")
    access_key_id: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SONIC_AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    )
    secret_access_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SONIC_AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    session_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SONIC_AWS_SESSION_TOKEN", "AWS_SESSION_TOKEN"),
    )
    credential_expiration: str | None = Field(
        default=None,
        alias="SONIC_AWS_CREDENTIAL_EXPIRATION",
    )
    system_instruction: str = Field(
        default=(
            "You are a realtime voice interface for a strictly grounded RAG assistant. "
            "For knowledge questions, call the answer_question tool and speak only the "
            "grounded answer returned by that tool. Keep spoken responses concise."
        ),
        alias="NOVA_SONIC_SYSTEM_INSTRUCTION",
    )
