from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from question_api.adapters.anthropic_llm import AnthropicLLMAdapter
from rag_core.settings import AnthropicSettings


class _Response:
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"content": [{"type": "text", "text": "grounded answer"}]}).encode()


@pytest.mark.asyncio
async def test_anthropic_llm_calls_messages_api_with_grounded_messages() -> None:
    settings = AnthropicSettings(
        ANTHROPIC_API_KEY="test-key",
        ANTHROPIC_DIRECT_MODEL="claude-test",
        ANTHROPIC_MAX_TOKENS=512,
        ANTHROPIC_TEMPERATURE=0.2,
        _env_file=None,
    )
    adapter = AnthropicLLMAdapter(settings)

    with patch("urllib.request.urlopen", return_value=_Response()) as urlopen:
        answer = await adapter.generate("system prompt", "user prompt")

    assert answer == "grounded answer"
    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.headers["X-api-key"] == "test-key"
    assert payload == {
        "model": "claude-test",
        "max_tokens": 512,
        "temperature": 0.2,
        "system": "system prompt",
        "messages": [{"role": "user", "content": "user prompt"}],
    }


@pytest.mark.asyncio
async def test_anthropic_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = AnthropicLLMAdapter(AnthropicSettings(_env_file=None))

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
        await adapter.generate("system prompt", "user prompt")
