"""FastAPI ``Depends`` providers backed by the composition root.

Tests override these via ``app.dependency_overrides[...]`` to inject fakes.
"""

from __future__ import annotations

from fastapi import Request

from vectorizer.core.composition import Container
from vectorizer.domain.vectorize_service import VectorizeService


def get_container(request: Request) -> Container:
    """Return the request-scoped container set up at startup."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("vectorizer container is not initialized on app.state")
    assert isinstance(container, Container)
    return container


def get_vectorize_service(request: Request) -> VectorizeService:
    return get_container(request).service
