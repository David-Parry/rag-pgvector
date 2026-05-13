"""App-level settings aggregator for question-api."""

from __future__ import annotations

from dataclasses import dataclass

from rag_core.settings import (
    AnthropicSettings,
    AwsBedrockSettings,
    DatabaseSettings,
    LoggingSettings,
    RetrievalSettings,
)


@dataclass(slots=True)
class QuestionApiSettings:
    logging: LoggingSettings
    anthropic: AnthropicSettings
    aws: AwsBedrockSettings
    database: DatabaseSettings
    retrieval: RetrievalSettings

    @classmethod
    def load(cls) -> QuestionApiSettings:
        return cls(
            logging=LoggingSettings(),
            anthropic=AnthropicSettings(),
            aws=AwsBedrockSettings(),
            database=DatabaseSettings(),
            retrieval=RetrievalSettings(),
        )
