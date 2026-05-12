"""``EmbeddingsPort`` adapter for AWS Bedrock Titan v2.

Identical behavior to the vectorizer's adapter; duplicated as a thin module
to keep the two projects deployable independently. Both call into the same
``BedrockEmbeddings`` class from ``langchain-aws``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from langchain_aws import BedrockEmbeddings

from rag_core.settings import AwsBedrockSettings


class TitanEmbeddingsAdapter:
    def __init__(self, settings: AwsBedrockSettings) -> None:
        self._settings = settings
        _ensure_bedrock_auth_env(settings)
        self._client = BedrockEmbeddings(
            model_id=settings.embedding_model_id,
            region_name=settings.region,
            model_kwargs={"dimensions": settings.embedding_dimensions},
        )

    async def embed_query(self, text: str) -> list[float]:
        return await self._client.aembed_query(text)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._client.aembed_documents(list(texts))

    @property
    def langchain_embeddings(self) -> BedrockEmbeddings:
        return self._client


def _ensure_bedrock_auth_env(settings: AwsBedrockSettings) -> None:
    if settings.bearer_token is not None:
        os.environ.setdefault(
            "AWS_BEARER_TOKEN_BEDROCK",
            settings.bearer_token.get_secret_value(),
        )
    if settings.access_key_id is not None:
        os.environ.setdefault(
            "AWS_ACCESS_KEY_ID",
            settings.access_key_id.get_secret_value(),
        )
    if settings.secret_access_key is not None:
        os.environ.setdefault(
            "AWS_SECRET_ACCESS_KEY",
            settings.secret_access_key.get_secret_value(),
        )
    os.environ.setdefault("AWS_REGION", settings.region)
    os.environ.setdefault("AWS_DEFAULT_REGION", settings.region)
