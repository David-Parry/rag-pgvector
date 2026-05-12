from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from question_api.adapters.bedrock_llm import BedrockLLMAdapter
from rag_core.settings import BedrockConnectionSettings


class _Provider:
    def __init__(self) -> None:
        self.client = MagicMock()
        self.client.converse.return_value = {
            "output": {"message": {"content": [{"text": "grounded answer"}]}}
        }
        self.connection = BedrockConnectionSettings(
            region="us-east-1",
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            embedding_model_id="amazon.titan-embed-text-v2:0",
            max_tokens=512,
            temperature=0.2,
        )

    def get_connection(self) -> BedrockConnectionSettings:
        return self.connection

    def get_runtime_client(self) -> MagicMock:
        return self.client


@pytest.mark.asyncio
async def test_bedrock_llm_calls_converse_with_grounded_messages() -> None:
    provider = _Provider()
    adapter = BedrockLLMAdapter(provider)

    answer = await adapter.generate("system prompt", "user prompt")

    assert answer == "grounded answer"
    provider.client.converse.assert_called_once_with(
        modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        system=[{"text": "system prompt"}],
        messages=[
            {
                "role": "user",
                "content": [{"text": "user prompt"}],
            }
        ],
        inferenceConfig={
            "maxTokens": 512,
            "temperature": 0.2,
        },
    )
