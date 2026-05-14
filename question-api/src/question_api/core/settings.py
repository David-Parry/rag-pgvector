"""App-level settings aggregator for question-api."""

from __future__ import annotations

from dataclasses import dataclass, field

from question_api.core.langgraph_redis_settings import LanggraphRedisSettings
from question_api.core.voice_settings import VoiceSettings
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
    langgraph_redis: LanggraphRedisSettings
    voice: VoiceSettings = field(default_factory=VoiceSettings)

    @classmethod
    def load(cls) -> QuestionApiSettings:
        return cls(
            logging=LoggingSettings(),
            anthropic=AnthropicSettings(),
            aws=AwsBedrockSettings(),
            database=DatabaseSettings(),
            retrieval=RetrievalSettings(),
            langgraph_redis=LanggraphRedisSettings(),
            voice=VoiceSettings(),
        )
