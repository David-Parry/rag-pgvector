from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from rag_evals.core.composition import build_container
from rag_evals.core.settings import EvalsSettings
from rag_evals.domain.golden import load_goldens

PACKAGE_ID = "BILLS-115hr1625enr"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_pgvector_retriever_recall_for_demo_bill() -> None:
    _skip_unless_required_env_is_present()
    settings = EvalsSettings.load()
    _skip_unless_demo_bill_is_ingested(settings.database.url)

    container = await build_container(settings)
    try:
        goldens = load_goldens(settings.deepeval.goldens_path)
        report = await container.benchmark.run(
            goldens,
            top_k_grid=[6],
            threshold_grid=[0.8],
        )
    finally:
        await container.aclose()

    row = report.row_for(top_k=6, threshold=0.8)
    assert row is not None
    assert row.recall >= 0.5


def _skip_unless_required_env_is_present() -> None:
    missing = [
        name
        for name in ("AWS_BEARER_TOKEN_BEDROCK", "ANTHROPIC_API_KEY", "DATABASE_URL")
        if not os.environ.get(name)
    ]
    if missing:
        pytest.skip("missing integration environment: " + ", ".join(missing))


def _skip_unless_demo_bill_is_ingested(database_url: str) -> None:
    try:
        with psycopg.connect(_to_psycopg_url(database_url), connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from rag_chunks where metadata->>'packageId' = %s",
                    (PACKAGE_ID,),
                )
                count = cursor.fetchone()
    except psycopg.Error as exc:
        pytest.skip("pgvector database is not reachable: " + str(exc))

    if count is None or int(count[0]) == 0:
        pytest.skip(PACKAGE_ID + " has not been ingested into pgvector")


def _to_psycopg_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = "postgresql" if parsed.scheme == "postgresql+psycopg" else parsed.scheme
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
