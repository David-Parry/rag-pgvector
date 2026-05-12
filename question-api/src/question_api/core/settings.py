"""App-level settings aggregator for question-api."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag_core.settings import (
    AnthropicSettings,
    AwsBedrockSettings,
    DatabaseSettings,
    LLMProvider,
    LoggingSettings,
    OllamaSettings,
    RetrievalSettings,
)


class _ProviderSelector(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    llm_provider: LLMProvider = Field(default="anthropic", alias="LLM_PROVIDER")


@dataclass(slots=True)
class QuestionApiSettings:
    logging: LoggingSettings
    aws: AwsBedrockSettings
    database: DatabaseSettings
    anthropic: AnthropicSettings
    ollama: OllamaSettings
    retrieval: RetrievalSettings
    llm_provider: LLMProvider

    @classmethod
    def load(cls) -> QuestionApiSettings:
        return cls(
            logging=LoggingSettings(),
            aws=AwsBedrockSettings(),
            database=DatabaseSettings(),
            anthropic=AnthropicSettings(),
            ollama=OllamaSettings(),
            retrieval=RetrievalSettings(),
            llm_provider=_ProviderSelector().llm_provider,
        )
