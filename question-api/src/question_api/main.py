"""FastAPI app factory + uvicorn entrypoint for the question-api service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from question_api.api.routes import router
from question_api.core.composition import build_container
from question_api.core.settings import QuestionApiSettings
from rag_core.logging import configure_logging, get_logger


def create_app(settings: QuestionApiSettings | None = None) -> FastAPI:
    resolved = settings or QuestionApiSettings.load()
    configure_logging(level=resolved.logging.log_level, fmt=resolved.logging.log_format)
    log = get_logger("question_api.bootstrap")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("question_api.starting", llm_provider="anthropic", llm_model=resolved.anthropic.model)
        container = await build_container(resolved)
        app.state.container = container
        try:
            log.info("question_api.ready")
            yield
        finally:
            log.info("question_api.shutting_down")
            await container.aclose()

    app = FastAPI(
        title="question-api",
        version="0.1.0",
        summary=(
            "Strictly-grounded RAG question answering: Bedrock Titan v2 retrieval "
            "over pgvector with switchable Anthropic / Ollama LLMs."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    log_level = os.environ.get("LOG_LEVEL", "DEBUG").lower()
    uvicorn.run(
        "question_api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
        log_config=None,
        log_level=log_level,
        access_log=True,
    )
