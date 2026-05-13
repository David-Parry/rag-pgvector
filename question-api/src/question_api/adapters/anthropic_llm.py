"""``LLMPort`` adapter for direct Anthropic Claude API calls."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from rag_core.settings import AnthropicSettings

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicLLMAdapter:
    """Wraps Anthropic Messages API without adding another runtime dependency."""

    PROVIDER = "anthropic"

    def __init__(self, settings: AnthropicSettings) -> None:
        self._settings = settings

    async def generate(self, system: str, user: str) -> str:
        return await asyncio.to_thread(self._generate_sync, system, user)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        yield await self.generate(system, user)

    def _generate_sync(self, system: str, user: str) -> str:
        api_key = self._settings.api_key.get_secret_value()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for question-api")

        payload = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "temperature": self._settings.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        request = urllib.request.Request(
            _ANTHROPIC_MESSAGES_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
                "x-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API request failed with HTTP {exc.code}: {body}") from exc
        return _extract_text(data)


def _extract_text(response: object) -> str:
    if not isinstance(response, dict):
        return str(response)
    content = response.get("content", [])
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif isinstance(item, dict):
            text = item.get("text")
            if text is not None:
                parts.append(str(text))
        else:
            parts.append(str(item))
    return "".join(parts)
