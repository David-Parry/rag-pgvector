"""Retriever benchmark orchestration over the shared ``VectorStorePort``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import structlog
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
)
from deepeval.test_case import LLMTestCase

from rag_core.ports import RetrievedChunk, VectorStorePort
from rag_evals.adapters.deepeval_retriever import to_retrieval_context
from rag_evals.domain.golden import Golden


class DeepEvalJudge(Protocol):
    def generate(self, prompt: str, schema: object | None = None) -> object: ...

    async def a_generate(self, prompt: str, schema: object | None = None) -> object: ...

    def get_model_name(self) -> str: ...


class Metric(Protocol):
    score: float | None

    def measure(self, test_case: LLMTestCase) -> float | None: ...


MetricFactory = Callable[[DeepEvalJudge], Sequence[Metric]]


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    top_k: int
    threshold: float
    precision: float
    recall: float
    relevancy: float
    cases: int


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    rows: tuple[BenchmarkRow, ...]

    def row_for(self, *, top_k: int, threshold: float) -> BenchmarkRow | None:
        for row in self.rows:
            if row.top_k == top_k and row.threshold == threshold:
                return row
        return None

    def best_by(self, metric_name: str) -> BenchmarkRow:
        if metric_name not in {"precision", "recall", "relevancy"}:
            raise ValueError("metric_name must be precision, recall, or relevancy")
        return max(self.rows, key=lambda row: getattr(row, metric_name))


class RetrieverBenchmark:
    """Run a grid search over top-k and cosine-distance threshold settings."""

    def __init__(
        self,
        *,
        store: VectorStorePort,
        judge: DeepEvalJudge,
        metric_factory: MetricFactory | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
        verbose_mode: bool = False,
    ) -> None:
        self._store = store
        self._judge = judge
        self._metric_factory = metric_factory or (
            lambda judge: default_metric_factory(judge, verbose_mode=verbose_mode)
        )
        self._log = logger or structlog.get_logger(__name__)

    async def run(
        self,
        goldens: Sequence[Golden],
        *,
        top_k_grid: Sequence[int],
        threshold_grid: Sequence[float],
    ) -> BenchmarkReport:
        rows: list[BenchmarkRow] = []
        total_cells = len(top_k_grid) * len(threshold_grid)
        self._log.info(
            "evals.benchmark_started",
            total_cells=total_cells,
            goldens=len(goldens),
            top_k_grid=list(top_k_grid),
            threshold_grid=list(threshold_grid),
            judge_model=self._judge.get_model_name(),
        )
        cell_number = 0
        for top_k in top_k_grid:
            for threshold in threshold_grid:
                cell_number += 1
                self._log.info(
                    "evals.benchmark_cell_started",
                    cell_number=cell_number,
                    total_cells=total_cells,
                    top_k=top_k,
                    threshold=threshold,
                )
                test_cases = await self._build_test_cases(
                    goldens,
                    top_k=top_k,
                    threshold=threshold,
                )
                self._log.info(
                    "evals.benchmark_cell_scoring_started",
                    cell_number=cell_number,
                    total_cells=total_cells,
                    top_k=top_k,
                    threshold=threshold,
                    cases=len(test_cases),
                )
                precision, recall, relevancy = await asyncio.to_thread(
                    _measure_scores,
                    self._metric_factory(self._judge),
                    test_cases,
                    self._log,
                    top_k,
                    threshold,
                )
                rows.append(
                    BenchmarkRow(
                        top_k=top_k,
                        threshold=threshold,
                        precision=precision,
                        recall=recall,
                        relevancy=relevancy,
                        cases=len(test_cases),
                    )
                )
                self._log.info(
                    "evals.benchmark_cell_completed",
                    top_k=top_k,
                    threshold=threshold,
                    precision=precision,
                    recall=recall,
                    relevancy=relevancy,
                )
        self._log.info("evals.benchmark_completed", total_cells=total_cells, rows=len(rows))
        return BenchmarkReport(rows=tuple(rows))

    async def _build_test_cases(
        self,
        goldens: Sequence[Golden],
        *,
        top_k: int,
        threshold: float,
    ) -> list[LLMTestCase]:
        test_cases: list[LLMTestCase] = []
        total_goldens = len(goldens)
        for case_number, golden in enumerate(goldens, start=1):
            self._log.info(
                "evals.retrieval_started",
                case_number=case_number,
                total_cases=total_goldens,
                top_k=top_k,
                threshold=threshold,
            )
            hits = await self._store.similarity_search(
                golden.question,
                k=top_k,
                metadata_filter=golden.metadata_filter or None,
            )
            kept = _apply_threshold(hits, threshold=threshold)
            self._log.info(
                "evals.retrieval_completed",
                case_number=case_number,
                total_cases=total_goldens,
                top_k=top_k,
                threshold=threshold,
                retrieved=len(hits),
                kept=len(kept),
            )
            test_cases.append(
                LLMTestCase(
                    input=golden.question,
                    actual_output="",
                    expected_output=golden.expected_output,
                    retrieval_context=to_retrieval_context(kept),
                    expected_retrieval_context=golden.expected_retrieval_context,
                )
            )
        return test_cases


def default_metric_factory(judge: DeepEvalJudge, *, verbose_mode: bool = False) -> Sequence[Metric]:
    return (
        ContextualPrecisionMetric(
            threshold=0.0,
            model=judge,
            include_reason=False,
            verbose_mode=verbose_mode,
        ),
        ContextualRecallMetric(
            threshold=0.0,
            model=judge,
            include_reason=False,
            verbose_mode=verbose_mode,
        ),
        ContextualRelevancyMetric(
            threshold=0.0,
            model=judge,
            include_reason=False,
            verbose_mode=verbose_mode,
        ),
    )


def _apply_threshold(
    hits: Sequence[RetrievedChunk],
    *,
    threshold: float,
) -> list[RetrievedChunk]:
    """Cosine distance from pgvector uses lower scores for closer chunks."""
    return [hit for hit in hits if hit.score <= threshold]


def _measure_scores(
    metrics: Sequence[Metric],
    test_cases: Sequence[LLMTestCase],
    logger: structlog.stdlib.BoundLogger,
    top_k: int,
    threshold: float,
) -> tuple[float, float, float]:
    if len(metrics) != 3:
        raise ValueError("metric_factory must return precision, recall, and relevancy metrics")
    scores = [
        _measure_metric(
            metric,
            test_cases,
            logger=logger,
            metric_name=metric_name,
            top_k=top_k,
            threshold=threshold,
        )
        for metric_name, metric in zip(("precision", "recall", "relevancy"), metrics, strict=True)
    ]
    return (scores[0], scores[1], scores[2])


def _measure_metric(
    metric: Metric,
    test_cases: Sequence[LLMTestCase],
    *,
    logger: structlog.stdlib.BoundLogger,
    metric_name: str,
    top_k: int,
    threshold: float,
) -> float:
    scores: list[float] = []
    total_cases = len(test_cases)
    logger.info(
        "evals.metric_started",
        metric=metric_name,
        metric_class=metric.__class__.__name__,
        cases=total_cases,
        top_k=top_k,
        threshold=threshold,
    )
    for case_number, test_case in enumerate(test_cases, start=1):
        logger.info(
            "evals.metric_case_started",
            metric=metric_name,
            case_number=case_number,
            total_cases=total_cases,
            top_k=top_k,
            threshold=threshold,
        )
        measured = metric.measure(test_case)
        score = metric.score if metric.score is not None else measured
        if score is not None:
            scores.append(float(score))
        logger.info(
            "evals.metric_case_completed",
            metric=metric_name,
            case_number=case_number,
            total_cases=total_cases,
            score=score,
            top_k=top_k,
            threshold=threshold,
        )
    if not scores:
        logger.info("evals.metric_completed", metric=metric_name, score=0.0)
        return 0.0
    average_score = sum(scores) / len(scores)
    logger.info(
        "evals.metric_completed",
        metric=metric_name,
        score=average_score,
        scored_cases=len(scores),
        total_cases=total_cases,
        top_k=top_k,
        threshold=threshold,
    )
    return average_score
