from __future__ import annotations

import asyncio

from rag_evals import cli


def test_configure_windows_event_loop_policy_uses_selector(monkeypatch) -> None:
    class FakeSelectorPolicy(asyncio.DefaultEventLoopPolicy):
        pass

    observed: list[asyncio.AbstractEventLoopPolicy] = []
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli.asyncio, "WindowsSelectorEventLoopPolicy", FakeSelectorPolicy, raising=False)
    monkeypatch.setattr(cli.asyncio, "set_event_loop_policy", observed.append)

    cli._configure_windows_event_loop_policy()

    assert isinstance(observed[0], FakeSelectorPolicy)


def test_configure_windows_event_loop_policy_ignores_non_windows(monkeypatch) -> None:
    observed: list[asyncio.AbstractEventLoopPolicy] = []
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(cli.asyncio, "set_event_loop_policy", observed.append)

    cli._configure_windows_event_loop_policy()

    assert observed == []
