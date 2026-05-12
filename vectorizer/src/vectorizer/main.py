"""FastAPI app factory + uvicorn entrypoint for the vectorizer service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rag_core.logging import configure_logging, get_logger
from vectorizer.api.routes import router
from vectorizer.core.composition import build_container
from vectorizer.core.settings import VectorizerSettings


def create_app(settings: VectorizerSettings | None = None) -> FastAPI:
    """Application factory. Settings can be injected for tests."""
    resolved = settings or VectorizerSettings.load()
    configure_logging(level=resolved.logging.log_level, fmt=resolved.logging.log_format)
    log = get_logger("vectorizer.bootstrap")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("vectorizer.starting")
        container = await build_container(resolved)
        app.state.container = container
        try:
            log.info("vectorizer.ready")
            yield
        finally:
            log.info("vectorizer.shutting_down")
            await container.aclose()

    app = FastAPI(
        title="vectorizer",
        version="0.1.0",
        summary=(
            "Pulls PDFs from api.govinfo.gov, extracts via PyMuPDF, embeds with "
            "Bedrock Titan v2, and upserts into pgvector."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    """Entrypoint used by ``[project.scripts] vectorizer``."""
    import uvicorn

    log_level = os.environ.get("LOG_LEVEL", "DEBUG").lower()
    uvicorn.run(
        "vectorizer.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
        log_config=None,
        log_level=log_level,
        access_log=True,
    )
