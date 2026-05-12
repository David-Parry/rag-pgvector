from __future__ import annotations

from collections.abc import Sequence

import pytest
from _evals_fakes import FakeStore, StubJudge, StubMetric, hit

from rag_evals.domain.benchmark import DeepEvalJudge, Metric, RetrieverBenchmark
from rag_evals.domain.golden import Golden


def _golden(question: str = "What are the restrictions?") -> Golden:
    return Golden(
        question=question,
        expected_output="Expected answer",
        expected_retrieval_context=["Sec. 7040"],
        metadata_filter={"packageId": "BILLS-115hr1625enr"},
    )


@pytest.mark.asyncio
async def test_benchmark_emits_one_row_per_grid_cell() -> None:
    metrics = (StubMetric(0.7), StubMetric(0.8), StubMetric(0.9))
    benchmark = RetrieverBenchmark(
        store=FakeStore([hit(1, 0.1)]),
        judge=StubJudge(),
        metric_factory=lambda judge: metrics,
    )

    report = await benchmark.run(
        [_golden()],
        top_k_grid=[3, 6],
        threshold_grid=[0.4, 0.8],
    )

    assert len(report.rows) == 4
    assert {(row.top_k, row.threshold) for row in report.rows} == {
        (3, 0.4),
        (3, 0.8),
        (6, 0.4),
        (6, 0.8),
    }
    assert report.best_by("recall").recall == 0.8


@pytest.mark.asyncio
async def test_benchmark_filters_hits_using_cosine_distance_threshold() -> None:
    precision = StubMetric(0.5)
    recall = StubMetric(0.6)
    relevancy = StubMetric(0.7)
    benchmark = RetrieverBenchmark(
        store=FakeStore([hit(1, 0.1), hit(2, 0.9), hit(3, 0.4)]),
        judge=StubJudge(),
        metric_factory=lambda judge: (precision, recall, relevancy),
    )

    report = await benchmark.run([_golden()], top_k_grid=[5], threshold_grid=[0.5])

    assert report.rows[0].precision == 0.5
    assert precision.observed_context_lengths == [2]
    assert recall.observed_context_lengths == [2]
    assert relevancy.observed_context_lengths == [2]


@pytest.mark.asyncio
async def test_benchmark_forwards_metadata_filter_and_top_k() -> None:
    store = FakeStore([hit(1, 0.1)])
    benchmark = RetrieverBenchmark(
        store=store,
        judge=StubJudge(),
        metric_factory=_stub_metric_factory,
    )

    await benchmark.run([_golden("Which section applies?")], top_k_grid=[6], threshold_grid=[0.8])

    assert store.search_calls == [
        {
            "query": "Which section applies?",
            "k": 6,
            "filter": {"packageId": "BILLS-115hr1625enr"},
        }
    ]


def _stub_metric_factory(judge: DeepEvalJudge) -> Sequence[Metric]:
    return (StubMetric(1.0), StubMetric(1.0), StubMetric(1.0))
