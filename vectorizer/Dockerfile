# syntax=docker/dockerfile:1.7
# Multi-stage build for the vectorizer pod.
# Build context MUST be the monorepo root because vectorizer depends on the
# rag-core workspace member.
#
#   docker build -t rag-pgvector/vectorizer:0.1.0 -f vectorizer/Dockerfile .
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

COPY --from=ghcr.io/astral-sh/uv:0.5.7 /uv /usr/local/bin/uv

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY libs/rag-core/pyproject.toml libs/rag-core/README.md libs/rag-core/
COPY libs/rag-core/src libs/rag-core/src
COPY vectorizer/pyproject.toml vectorizer/README.md vectorizer/
COPY vectorizer/src vectorizer/src
COPY question-api/pyproject.toml question-api/README.md question-api/
COPY question-api/src question-api/src

RUN --mount=type=secret,id=custom_ca,dst=/tmp/custom-ca.crt,required=false \
    apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && if [ -f /tmp/custom-ca.crt ]; then \
      cp /tmp/custom-ca.crt /usr/local/share/ca-certificates/custom-ca.crt; \
    fi \
 && update-ca-certificates \
 && if [ -f /tmp/custom-ca.crt ]; then \
      cat /tmp/custom-ca.crt >> /etc/ssl/certs/ca-certificates.crt; \
    fi \
 && rm -rf /var/lib/apt/lists/* \
 && uv sync --package vectorizer --frozen --no-dev

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

CMD ["vectorizer"]
