"""``LLMPort`` adapter for a host-resident Ollama via ``langchain-ollama``.

Defaults to ``http://host.docker.internal:11434`` so the question-api pod can
reach the Ollama process running on the Docker Desktop host (the laptop).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from rag_core.settings import OllamaSettings


class OllamaLLMAdapter:
    """Wraps ``ChatOllama``."""

    PROVIDER = "ollama"

    def __init__(self, settings: OllamaSettings) -> None:
        self._client = ChatOllama(
            model=settings.model,
            base_url=settings.base_url,
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
