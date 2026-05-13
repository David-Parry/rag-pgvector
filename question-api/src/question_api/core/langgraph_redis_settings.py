"""Redis checkpointer settings for LangGraph (question-api)."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LanggraphRedisSettings(BaseSettings):
    """Connection and TTL for ``AsyncRedisSaver`` (session-scoped checkpoints)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://127.0.0.1:6379",
        validation_alias=AliasChoices("LANGGRAPH_REDIS_URL", "REDIS_URL"),
    )
    session_checkpoint_ttl_days: int = Field(
        default=5,
        ge=1,
        le=90,
        alias="SESSION_CHECKPOINT_TTL_DAYS",
    )
    refresh_on_read: bool = Field(
        default=True,
        alias="SESSION_CHECKPOINT_TTL_REFRESH_ON_READ",
    )

    @property
    def ttl_minutes(self) -> float:
        """``langgraph-checkpoint-redis`` ``default_ttl`` is expressed in minutes."""
        return float(self.session_checkpoint_ttl_days * 24 * 60)

    def ttl_config(self) -> dict[str, object]:
        return {
            "default_ttl": self.ttl_minutes,
            "refresh_on_read": self.refresh_on_read,
        }


def sanitize_redis_url_for_log(url: str) -> str:
    """Return ``host:port`` or ``host:port/db`` for structured logs. Omits userinfo and passwords."""
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    if parsed.port is not None:
        port = parsed.port
    else:
        port = 6379
    path = (parsed.path or "").strip("/")
    return f"{host}:{port}/{path}" if path else f"{host}:{port}"
