"""Command-line runner for the pgvector retriever benchmark."""

from __future__ import annotations

import asyncio
import html
import os
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass

from rag_evals.core.composition import build_container
from rag_evals.core.settings import EvalsSettings
from rag_evals.domain.benchmark import BenchmarkReport, BenchmarkRow
from rag_evals.domain.golden import Golden, load_goldens
from rag_core.logging import configure_logging


@dataclass(frozen=True, slots=True)
class EvalGates:
    min_precision: float
    min_recall: float
    min_relevancy: float


def main() -> None:
    _configure_windows_event_loop_policy()
    asyncio.run(_run())


def _configure_windows_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is None:
        return
    asyncio.set_event_loop_policy(selector_policy())


async def _run() -> None:
    with redirect_stdout(sys.stderr):
        settings = EvalsSettings.load()
        configure_logging(level=settings.logging.log_level, fmt=settings.logging.log_format)
        goldens = _apply_package_override(
            load_goldens(settings.deepeval.goldens_path),
            package_id=os.environ.get("PACKAGE_ID"),
        )
        container = await build_container(settings)
        try:
            report = await container.benchmark.run(
                goldens,
                top_k_grid=settings.deepeval.top_k_grid,
                threshold_grid=settings.deepeval.threshold_grid,
            )
        finally:
            await container.aclose()
    print(
        _format_report(
            report,
            gates=_load_gates(),
            file_type=settings.deepeval.report_file_type,
        )
    )


def _apply_package_override(goldens: list[Golden], *, package_id: str | None) -> list[Golden]:
    if not package_id:
        return goldens
    return [
        golden.model_copy(
            update={"metadata_filter": {**golden.metadata_filter, "packageId": package_id}}
        )
        for golden in goldens
    ]


def _load_gates() -> EvalGates:
    return EvalGates(
        min_precision=_float_env("DEEPEVAL_MIN_PRECISION", 0.5),
        min_recall=_float_env("DEEPEVAL_MIN_RECALL", 0.5),
        min_relevancy=_float_env("DEEPEVAL_MIN_RELEVANCY", 0.5),
    )


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _format_report(report: BenchmarkReport, *, gates: EvalGates, file_type: str) -> str:
    if file_type == "html":
        return _to_html(report, gates=gates)
    return _to_markdown(report, gates=gates)


def _to_markdown(report: BenchmarkReport, *, gates: EvalGates) -> str:
    passed_rows = [row for row in report.rows if _row_passes(row, gates)]
    overall_status = "PASS" if len(passed_rows) > 0 else "FAIL"
    best_balanced = max(report.rows, key=_balanced_score)
    lines = [
        "## Summary",
        "",
        f"- Overall result: **{overall_status}**",
        (
            "- Gates: "
            f"precision >= {gates.min_precision:.3f}, "
            f"recall >= {gates.min_recall:.3f}, "
            f"relevancy >= {gates.min_relevancy:.3f}"
        ),
        f"- Passing cells: {len(passed_rows)} of {len(report.rows)}",
        (
            "- Best balanced cell: "
            f"top_k={best_balanced.top_k}, threshold={best_balanced.threshold:.2f}, "
            f"average={_balanced_score(best_balanced):.3f}"
        ),
        "",
        "## Results",
        "",
        "| status | top_k | threshold | precision | recall | relevancy | average | cases |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.rows:
        status = "PASS" if _row_passes(row, gates) else "FAIL"
        lines.append(
            "| "
            + " | ".join(
                [
                    status,
                    str(row.top_k),
                    f"{row.threshold:.2f}",
                    f"{row.precision:.3f}",
                    f"{row.recall:.3f}",
                    f"{row.relevancy:.3f}",
                    f"{_balanced_score(row):.3f}",
                    str(row.cases),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Best precision: " + _format_best(report, "precision"),
            "Best recall: " + _format_best(report, "recall"),
            "Best relevancy: " + _format_best(report, "relevancy"),
        ]
    )
    return "\n".join(lines)


def _to_html(report: BenchmarkReport, *, gates: EvalGates) -> str:
    passed_rows = [row for row in report.rows if _row_passes(row, gates)]
    overall_status = "PASS" if len(passed_rows) > 0 else "FAIL"
    best_balanced = max(report.rows, key=_balanced_score)
    lines = [
        "<section>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li>Overall result: <strong>{overall_status}</strong></li>",
        (
            "<li>Gates: "
            f"precision &gt;= {gates.min_precision:.3f}, "
            f"recall &gt;= {gates.min_recall:.3f}, "
            f"relevancy &gt;= {gates.min_relevancy:.3f}</li>"
        ),
        f"<li>Passing cells: {len(passed_rows)} of {len(report.rows)}</li>",
        (
            "<li>Best balanced cell: "
            f"top_k={best_balanced.top_k}, threshold={best_balanced.threshold:.2f}, "
            f"average={_balanced_score(best_balanced):.3f}</li>"
        ),
        "</ul>",
        "</section>",
        "<section>",
        "<h2>Results</h2>",
        "<table>",
        "<thead>",
        (
            "<tr><th>status</th><th>top_k</th><th>threshold</th><th>precision</th>"
            "<th>recall</th><th>relevancy</th><th>average</th><th>cases</th></tr>"
        ),
        "</thead>",
        "<tbody>",
    ]
    for row in report.rows:
        status = "PASS" if _row_passes(row, gates) else "FAIL"
        lines.append(
            "<tr>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{row.top_k}</td>"
            f"<td>{row.threshold:.2f}</td>"
            f"<td>{row.precision:.3f}</td>"
            f"<td>{row.recall:.3f}</td>"
            f"<td>{row.relevancy:.3f}</td>"
            f"<td>{_balanced_score(row):.3f}</td>"
            f"<td>{row.cases}</td>"
            "</tr>"
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
            "<section>",
            "<h2>Best Metrics</h2>",
            "<ul>",
            f"<li>Best precision: {html.escape(_format_best(report, 'precision'))}</li>",
            f"<li>Best recall: {html.escape(_format_best(report, 'recall'))}</li>",
            f"<li>Best relevancy: {html.escape(_format_best(report, 'relevancy'))}</li>",
            "</ul>",
            "</section>",
        ]
    )
    return "\n".join(lines)


def _row_passes(row: BenchmarkRow, gates: EvalGates) -> bool:
    return (
        row.precision >= gates.min_precision
        and row.recall >= gates.min_recall
        and row.relevancy >= gates.min_relevancy
    )


def _balanced_score(row: BenchmarkRow) -> float:
    return (row.precision + row.recall + row.relevancy) / 3


def _format_best(report: BenchmarkReport, metric_name: str) -> str:
    row = report.best_by(metric_name)
    return (
        f"top_k={row.top_k}, threshold={row.threshold:.2f}, "
        f"{metric_name}={getattr(row, metric_name):.3f}"
    )


if __name__ == "__main__":
    main()
