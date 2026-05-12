"""FastAPI ``Depends`` providers backed by the composition root."""

from __future__ import annotations

from fastapi import Request

from question_api.core.composition import Container
from question_api.domain.ask_service import AskService


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("question-api container is not initialized on app.state")
    assert isinstance(container, Container)
    return container


def get_ask_service(request: Request) -> AskService:
    return get_container(request).service
