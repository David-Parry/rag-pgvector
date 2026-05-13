from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy")
        return selector_policy()
    return asyncio.get_event_loop_policy()
