# Multi-stage build for the question-api pod.
# Build context MUST be the monorepo root.
#
#   docker build -t rag-pgvector/question-api:0.1.0 -f question-api/Dockerfile .
#
# Corporate / JFrog: see documentation/DOCKER_PYPI_MIRROR.md (same pattern as vectorizer).
#
# When the index URL contains `user:token@`, the builder merges credentials into
# `/root/.netrc` and uses a credential-free index URL so artifact downloads authenticate.
#
# Docker Desktop's built-in Kubernetes shares the Docker daemon, so this image
# is visible to the cluster without any registry push or load step.

# ----- Stage 1: builder -------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NATIVE_TLS=true \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY scripts/docker/rewrite_uv_lock_for_mirror.py scripts/docker/rewrite_uv_lock_for_public_pypi.py scripts/docker/prepare_artifactory_for_uv.py scripts/docker/check_uv_lock_artifact_access.py scripts/docker/uv_sync_with_fallback.sh scripts/docker/
COPY libs/rag-core/pyproject.toml libs/rag-core/README.md libs/rag-core/
COPY libs/rag-core/src libs/rag-core/src
COPY vectorizer/pyproject.toml vectorizer/README.md vectorizer/
COPY vectorizer/src vectorizer/src
COPY question-api/pyproject.toml question-api/README.md question-api/
COPY question-api/src question-api/src

ARG UV_DEFAULT_INDEX=

RUN --mount=type=secret,id=uv_default_index,required=false \
    --mount=type=secret,id=ssl_cert_bundle,required=false \
    --mount=type=secret,id=netrc,required=false \
    sh scripts/docker/uv_sync_with_fallback.sh question-api

# ----- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/.venv/bin:$PATH"

RUN groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --home-dir /home/app --create-home app

WORKDIR /workspace

COPY --from=builder --chown=app:app /workspace /workspace

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3); sys.exit(0)" || exit 1

CMD ["question-api"]
