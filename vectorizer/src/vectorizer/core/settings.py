"""App-level settings aggregator for vectorizer."""

from __future__ import annotations

from dataclasses import dataclass

from rag_core.settings import (
    AwsBedrockSettings,
    DatabaseSettings,
    GovInfoSettings,
    LoggingSettings,
)


@dataclass(slots=True)
class VectorizerSettings:
    logging: LoggingSettings
    aws: AwsBedrockSettings
    database: DatabaseSettings
    govinfo: GovInfoSettings

    @classmethod
    def load(cls) -> VectorizerSettings:
        """Load all sub-settings from the environment / .env file."""
        return cls(
            logging=LoggingSettings(),
            aws=AwsBedrockSettings(),
            database=DatabaseSettings(),
            govinfo=GovInfoSettings(),
        )
