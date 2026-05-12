"""DeepEval judge adapter backed by Anthropic Claude or local Ollama."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from deepeval.models import DeepEvalBaseLLM
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from rag_core.settings import AnthropicSettings, OllamaSettings

JudgeProvider = Literal["anthropic", "ollama"]


class DeepEvalJudgeAdapter(DeepEvalBaseLLM):
    """DeepEval LLM wrapper that reuses the repository's existing LLM settings."""

    def __init__(
        self,
        *,
        provider: JudgeProvider,
        anthropic: AnthropicSettings,
        ollama: OllamaSettings,
    ) -> None:
        self._provider = provider
        self._model = _build_model(provider=provider, anthropic=anthropic, ollama=ollama)
        super().__init__(model=self.get_model_name())

    def load_model(self) -> BaseChatModel:
        return self._model

    def generate(self, prompt: str, schema: object | None = None) -> Any:
        if schema is not None:
            return asyncio.run(self.a_generate(prompt, schema=schema))
        response = self._model.invoke([HumanMessage(content=prompt)])
        return _content_to_text(response.content)

    async def a_generate(self, prompt: str, schema: object | None = None) -> Any:
        if schema is not None:
            structured = self._model.with_structured_output(schema)
            return await structured.ainvoke([HumanMessage(content=prompt)])
        response = await self._model.ainvoke([HumanMessage(content=prompt)])
        return _content_to_text(response.content)

    def get_model_name(self) -> str:
        return f"{self._provider}:{getattr(self._model, 'model_name', self._provider)}"


def _build_model(
    *,
    provider: JudgeProvider,
    anthropic: AnthropicSettings,
    ollama: OllamaSettings,
) -> BaseChatModel:
    if provider == "anthropic":
        api_key = anthropic.api_key.get_secret_value()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when DEEPEVAL_JUDGE_PROVIDER=anthropic")
        return ChatAnthropic(
            model=anthropic.model,
            api_key=api_key,
            max_tokens=anthropic.max_tokens,
            temperature=anthropic.temperature,
            timeout=anthropic.timeout_seconds,
        )
    return ChatOllama(model=ollama.model, base_url=ollama.base_url)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)
