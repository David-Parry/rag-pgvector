"""FastAPI app factory + uvicorn entrypoint for the question-api service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from question_api.api.routes import router
from question_api.core.composition import build_container
from question_api.core.settings import QuestionApiSettings
from question_api.voice.routes import close_voice_sessions
from question_api.voice.routes import router as voice_router
from rag_core.logging import configure_logging, get_logger


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)


def _cors_origins_from_env() -> list[str]:
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "")
    if not raw.strip():
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app(settings: QuestionApiSettings | None = None) -> FastAPI:
    resolved = settings or QuestionApiSettings.load()
    configure_logging(level=resolved.logging.log_level, fmt=resolved.logging.log_format)
    log = get_logger("question_api.bootstrap")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("question_api.starting", llm_model=resolved.anthropic.model)
        container = await build_container(resolved)
        app.state.container = container
        try:
            log.info("question_api.ready")
            yield
        finally:
            log.info("question_api.shutting_down")
            await close_voice_sessions()
            await container.aclose()

    app = FastAPI(
        title="question-api",
        version="0.1.0",
        summary=(
            "Strictly-grounded RAG question answering: Bedrock Titan v2 retrieval "
            "over pgvector with Anthropic Claude answer generation."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(voice_router)
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
