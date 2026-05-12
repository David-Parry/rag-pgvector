"""Pydantic-Settings models shared by both apps.

Each app composes only the sub-sections it needs via dependency injection in
its ``core/composition.py`` module (Dependency Inversion + DRY).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class _BaseEnvSettings(BaseSettings):
    """Common config: read from .env and process env, ignore unknown keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class LoggingSettings(_BaseEnvSettings):
    log_level: str = Field(default="DEBUG", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")


class AwsBedrockSettings(_BaseEnvSettings):
    region: str = Field(default="us-east-1", alias="AWS_REGION")
    embedding_model_id: str = Field(
        default="amazon.titan-embed-text-v2:0",
        alias="BEDROCK_EMBEDDING_MODEL_ID",
    )
    embedding_dimensions: int = Field(default=1024, alias="BEDROCK_EMBEDDING_DIMENSIONS")
    bearer_token: SecretStr | None = Field(default=None, alias="AWS_BEARER_TOKEN_BEDROCK")
    access_key_id: SecretStr | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    secret_access_key: SecretStr | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    @property
    def embedding_model_name(self) -> str:
        """Bedrock model id with the ``-v<major>`` family suffix and ``:<rev>``
        revision suffix both stripped.

        For ``amazon.titan-embed-text-v2:0`` this returns
        ``amazon.titan-embed-text``. Stored alongside each chunk row so the
        corpus is self-describing (you can re-derive *which* embedding model
        family produced a vector without consulting deploy history).
        """
        name, _ = _parse_embedding_model_id(self.embedding_model_id)
        return name

    @property
    def embedding_model_version(self) -> str:
        """Combined family-version + revision in ``<major>.<rev>`` form.

        For ``amazon.titan-embed-text-v2:0`` this returns ``2.0`` (the ``v2``
        family version joined to the ``:0`` Bedrock revision). When only one
        of the two segments is present we degrade gracefully:

            amazon.titan-embed-text-v2   -> "2"     (no Bedrock :rev)
            cohere.embed-english-v3:0    -> "3.0"
            meta.llama3-70b:0            -> "0"     (no -v<n> family suffix)
            something-without-version    -> ""      (neither)
        """
        _, version = _parse_embedding_model_id(self.embedding_model_id)
        return version


class DatabaseSettings(_BaseEnvSettings):
    url: str = Field(
        default="postgresql+psycopg://rag:rag@localhost:5432/rag",
        alias="DATABASE_URL",
    )
    collection: str = Field(default="rag_chunks", alias="PGVECTOR_COLLECTION")


class GovInfoSettings(_BaseEnvSettings):
    api_key: SecretStr = Field(default=SecretStr(""), alias="GOVINFO_API_KEY")
    base_url: str = Field(default="https://api.govinfo.gov", alias="GOVINFO_BASE_URL")


class AnthropicSettings(_BaseEnvSettings):
    api_key: SecretStr = Field(default=SecretStr(""), alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-sonnet-4-5", alias="ANTHROPIC_MODEL")


class OllamaSettings(_BaseEnvSettings):
    base_url: str = Field(
        default="http://host.docker.internal:11434",
        alias="OLLAMA_BASE_URL",
    )
    model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")


class RetrievalSettings(_BaseEnvSettings):
    top_k: int = Field(default=5, alias="RETRIEVAL_TOP_K")
    score_threshold: float = Field(default=0.25, alias="RETRIEVAL_SCORE_THRESHOLD")


LLMProvider = Literal["anthropic", "ollama"]


# Bedrock model ids follow the convention `<vendor>.<family>-v<major>:<rev>`,
# e.g. `amazon.titan-embed-text-v2:0` or `cohere.embed-english-v3:0`. We split
# the id into two human-meaningful pieces so each pgvector row records *which*
# model family (`amazon.titan-embed-text`) and *which* combined version
# (`2.0`) produced its vector. Anchored at end-of-string so a stray `-v<n>` or
# `:<n>` mid-id never gets mistaken for the version segments.
_BEDROCK_MODEL_ID_RE = re.compile(
    r"""
    ^
    (?P<name>.+?)             # family / vendor prefix (non-greedy)
    (?:-v(?P<major>\d+))?     # optional `-v<major>` family suffix
    (?::(?P<rev>\d+))?        # optional `:<rev>` Bedrock revision suffix
    $
    """,
    re.VERBOSE,
)


def _parse_embedding_model_id(model_id: str) -> tuple[str, str]:
    """Split a Bedrock-style model id into ``(family_name, combined_version)``.

    The combined version is ``<major>.<rev>`` when both are present, else
    whichever single segment is present, else ``""``.

        amazon.titan-embed-text-v2:0 -> ('amazon.titan-embed-text', '2.0')
        amazon.titan-embed-text-v2   -> ('amazon.titan-embed-text', '2')
        cohere.embed-english-v3:0    -> ('cohere.embed-english',   '3.0')
        meta.llama3-70b:0            -> ('meta.llama3-70b',        '0')
        plain-model-id               -> ('plain-model-id',         '')
    """
    match = _BEDROCK_MODEL_ID_RE.match(model_id)
    if match is None:  # pragma: no cover — pattern is total over non-empty strings
        return model_id, ""
    name = match.group("name")
    major = match.group("major")
    rev = match.group("rev")
    if major and rev is not None:
        version = f"{major}.{rev}"
    elif major:
        version = major
    elif rev is not None:
        version = rev
    else:
        version = ""
    return name, version
