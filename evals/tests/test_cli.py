from __future__ import annotations

import asyncio

from rag_evals import cli
from rag_evals.domain.benchmark import BenchmarkReport, BenchmarkRow


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


def test_to_markdown_includes_pass_fail_summary() -> None:
    report = BenchmarkReport(
        rows=(
            BenchmarkRow(
                top_k=3,
                threshold=0.6,
                precision=0.4,
                recall=1.0,
                relevancy=1.0,
                cases=1,
            ),
            BenchmarkRow(
                top_k=3,
                threshold=0.2,
                precision=0.0,
                recall=0.0,
                relevancy=0.0,
                cases=1,
            ),
        )
    )

    markdown = cli._to_markdown(
        report,
        gates=cli.EvalGates(min_precision=0.3, min_recall=0.5, min_relevancy=0.5),
    )

    assert "Overall result: **PASS**" in markdown
    assert "| PASS | 3 | 0.60 | 0.400 | 1.000 | 1.000 | 0.800 | 1 |" in markdown
    assert "| FAIL | 3 | 0.20 | 0.000 | 0.000 | 0.000 | 0.000 | 1 |" in markdown


def test_format_report_can_emit_html() -> None:
    report = BenchmarkReport(
        rows=(
            BenchmarkRow(
                top_k=3,
                threshold=0.6,
                precision=0.4,
                recall=1.0,
                relevancy=1.0,
                cases=1,
            ),
        )
    )

    html = cli._format_report(
        report,
        gates=cli.EvalGates(min_precision=0.3, min_recall=0.5, min_relevancy=0.5),
        file_type="html",
    )

    assert "<h2>Summary</h2>" in html
    assert "<td>PASS</td>" in html
    assert "<td>0.60</td>" in html
