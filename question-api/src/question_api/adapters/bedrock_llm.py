"""``LLMPort`` adapter for Anthropic Claude through AWS Bedrock."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from rag_core.bedrock import BedrockRuntimeProvider
from rag_core.settings import BedrockConnectionSettings


class _BedrockProvider(Protocol):
    def get_connection(self) -> BedrockConnectionSettings:
        ...

    def get_runtime_client(self) -> Any:  # Any: boto3 clients are dynamically generated.
        ...


class BedrockLLMAdapter:
    """Wraps Bedrock Runtime ``converse`` for Claude-compatible chat models."""

    PROVIDER = "bedrock"

    def __init__(self, provider: _BedrockProvider | BedrockRuntimeProvider) -> None:
        self._provider = provider

    async def generate(self, system: str, user: str) -> str:
        return await asyncio.to_thread(self._generate_sync, system, user)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        yield await self.generate(system, user)

    def _generate_sync(self, system: str, user: str) -> str:
        connection = self._provider.get_connection()
        if not connection.model_id:
            raise ValueError("ANTHROPIC_MODEL is required in the Bedrock connection settings")

        response = self._provider.get_runtime_client().converse(
            modelId=connection.model_id,
            system=[{"text": system}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user}],
                }
            ],
            inferenceConfig={
                "maxTokens": connection.max_tokens,
                "temperature": connection.temperature,
            },
        )
        return _extract_text(response)


def _extract_text(response: object) -> str:
    if not isinstance(response, dict):
        return str(response)
    content_blocks = (
        response.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    return "".join(
        str(item.get("text", item)) if isinstance(item, dict) else str(item)
        for item in content_blocks
    )
