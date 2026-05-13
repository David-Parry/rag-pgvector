"""App-level settings aggregate for retriever evaluations."""

from __future__ import annotations

from dataclasses import dataclass

from rag_core.settings import (
    AnthropicSettings,
    AwsBedrockSettings,
    DatabaseSettings,
    DeepEvalSettings,
    LoggingSettings,
    OllamaSettings,
)


@dataclass(slots=True)
class EvalsSettings:
    logging: LoggingSettings
    anthropic: AnthropicSettings
    aws: AwsBedrockSettings
    database: DatabaseSettings
    ollama: OllamaSettings
    deepeval: DeepEvalSettings

    @classmethod
    def load(cls) -> EvalsSettings:
        return cls(
            logging=LoggingSettings(),
            anthropic=AnthropicSettings(),
            aws=AwsBedrockSettings(),
            database=DatabaseSettings(),
            ollama=OllamaSettings(),
            deepeval=DeepEvalSettings(),
        )
