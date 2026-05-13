from __future__ import annotations

import pytest

from question_api.core.settings import QuestionApiSettings
from question_api.main import create_app
from rag_core.settings import (
    AnthropicSettings,
    AwsBedrockSettings,
    DatabaseSettings,
    LoggingSettings,
    RetrievalSettings,
)


class _FakeContainer:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_lifespan_logs_anthropic_model_without_provider_setting(monkeypatch) -> None:
    container = _FakeContainer()

    async def fake_build_container(settings: QuestionApiSettings) -> _FakeContainer:
        return container

    monkeypatch.setattr("question_api.main.build_container", fake_build_container)
    settings = QuestionApiSettings(
        logging=LoggingSettings(LOG_FORMAT="console", _env_file=None),
        anthropic=AnthropicSettings(
            ANTHROPIC_API_KEY="test-key",
            ANTHROPIC_DIRECT_MODEL="claude-test",
            _env_file=None,
        ),
        aws=AwsBedrockSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        retrieval=RetrievalSettings(_env_file=None),
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert app.state.container is container

    assert container.closed is True
