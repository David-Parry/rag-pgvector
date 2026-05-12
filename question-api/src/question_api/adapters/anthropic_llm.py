"""``LLMPort`` adapter for Anthropic Claude via ``langchain-anthropic``."""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from rag_core.settings import AnthropicSettings


class AnthropicLLMAdapter:
    """Wraps ``ChatAnthropic``."""

    PROVIDER = "anthropic"

    def __init__(self, settings: AnthropicSettings) -> None:
        api_key = settings.api_key.get_secret_value()
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        self._client = ChatAnthropic(
            model=settings.model,
            api_key=settings.api_key,
            timeout=120.0,
            max_retries=2,
        )

    async def generate(self, system: str, user: str) -> str:
        response = await self._client.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        content = response.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        async for chunk in self._client.astream(
            [SystemMessage(content=system), HumanMessage(content=user)]
        ):
            content = chunk.content
            if isinstance(content, str):
                yield content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if text:
                            yield str(text)
