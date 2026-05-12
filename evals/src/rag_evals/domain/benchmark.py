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
    ) -> None:
        self._store = store
        self._judge = judge
        self._metric_factory = metric_factory or default_metric_factory
        self._log = logger or structlog.get_logger(__name__)

    async def run(
        self,
        goldens: Sequence[Golden],
        *,
        top_k_grid: Sequence[int],
        threshold_grid: Sequence[float],
    ) -> BenchmarkReport:
        rows: list[BenchmarkRow] = []
        for top_k in top_k_grid:
            for threshold in threshold_grid:
                test_cases = await self._build_test_cases(
                    goldens,
                    top_k=top_k,
                    threshold=threshold,
                )
                precision, recall, relevancy = await asyncio.to_thread(
                    _measure_scores,
                    self._metric_factory(self._judge),
                    test_cases,
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
        return BenchmarkReport(rows=tuple(rows))

    async def _build_test_cases(
        self,
        goldens: Sequence[Golden],
        *,
        top_k: int,
        threshold: float,
    ) -> list[LLMTestCase]:
        test_cases: list[LLMTestCase] = []
        for golden in goldens:
            hits = await self._store.similarity_search(
                golden.question,
                k=top_k,
                metadata_filter=golden.metadata_filter or None,
            )
            kept = _apply_threshold(hits, threshold=threshold)
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


def default_metric_factory(judge: DeepEvalJudge) -> Sequence[Metric]:
    return (
        ContextualPrecisionMetric(threshold=0.0, model=judge, include_reason=False),
        ContextualRecallMetric(threshold=0.0, model=judge, include_reason=False),
        ContextualRelevancyMetric(threshold=0.0, model=judge, include_reason=False),
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
) -> tuple[float, float, float]:
    if len(metrics) != 3:
        raise ValueError("metric_factory must return precision, recall, and relevancy metrics")
    scores = [_measure_metric(metric, test_cases) for metric in metrics]
    return (scores[0], scores[1], scores[2])


def _measure_metric(metric: Metric, test_cases: Sequence[LLMTestCase]) -> float:
    scores: list[float] = []
    for test_case in test_cases:
        measured = metric.measure(test_case)
        score = metric.score if metric.score is not None else measured
        if score is not None:
            scores.append(float(score))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
