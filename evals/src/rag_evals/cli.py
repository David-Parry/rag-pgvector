"""Command-line runner for the pgvector retriever benchmark."""

from __future__ import annotations

import asyncio
import os

from rag_evals.core.composition import build_container
from rag_evals.core.settings import EvalsSettings
from rag_evals.domain.benchmark import BenchmarkReport
from rag_evals.domain.golden import Golden, load_goldens


def main() -> None:
    asyncio.run(_run())


async def _run() -> None:
    settings = EvalsSettings.load()
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
    print(_to_markdown(report))


def _apply_package_override(goldens: list[Golden], *, package_id: str | None) -> list[Golden]:
    if not package_id:
        return goldens
    return [
        golden.model_copy(
            update={"metadata_filter": {**golden.metadata_filter, "packageId": package_id}}
        )
        for golden in goldens
    ]


def _to_markdown(report: BenchmarkReport) -> str:
    lines = [
        "| top_k | threshold | precision | recall | relevancy | cases |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.top_k),
                    f"{row.threshold:.2f}",
                    f"{row.precision:.3f}",
                    f"{row.recall:.3f}",
                    f"{row.relevancy:.3f}",
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


def _format_best(report: BenchmarkReport, metric_name: str) -> str:
    row = report.best_by(metric_name)
    return (
        f"top_k={row.top_k}, threshold={row.threshold:.2f}, "
        f"{metric_name}={getattr(row, metric_name):.3f}"
    )


if __name__ == "__main__":
    main()
