# Multi-stage build for the vectorizer pod.
# Build context MUST be the monorepo root because vectorizer depends on rag-core.
#
#   docker build -t rag-pgvector/vectorizer:0.1.0 -f vectorizer/Dockerfile .
#
# Optional corporate TLS — see documentation/DOCKER_PYPI_MIRROR.md
#
# When the index URL contains `user:token@`, the builder merges credentials into
# `/root/.netrc` and uses a credential-free `PIP_INDEX_URL` (see
# `scripts/docker/prepare_artifactory_for_pip.py`).
#
# Docker Desktop's built-in Kubernetes shares the Docker daemon, so this image
# is visible to the cluster without any registry push or load step.

# ----- Stage 1: builder -------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY scripts/docker/pip_install_with_fallback.sh scripts/docker/prepare_artifactory_for_pip.py scripts/docker/
COPY requirements/docker-vectorizer.txt requirements/
COPY libs/rag-core/pyproject.toml libs/rag-core/README.md libs/rag-core/
COPY libs/rag-core/src libs/rag-core/src
COPY vectorizer/pyproject.toml vectorizer/README.md vectorizer/
COPY vectorizer/src vectorizer/src

# Optional: PEP 503 index (JFrog virtual PyPI, etc.). Prefer secret `pip_index_url`
# (one line) over ARG to avoid creds in image history. Legacy secret `uv_default_index`
# is still read by the install script.
#
# Optional: mount your host global pip.ini as secret `pip_config`; the install script
# copies it to `/etc/pip.conf` so pip uses `index-url`, `trusted-host`, `extra-index-url`,
# etc. Set `RAG_DOCKER_PIP_CONFIG_FILE` when calling docker build (see DOCKER_PYPI_MIRROR.md).
ARG PIP_INDEX_URL=
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

RUN chmod +x scripts/docker/pip_install_with_fallback.sh

RUN --mount=type=secret,id=pip_index_url,required=false \
    --mount=type=secret,id=uv_default_index,required=false \
    --mount=type=secret,id=pip_config,required=false \
    --mount=type=secret,id=netrc,required=false \
    --mount=type=secret,id=ssl_cert_bundle,required=false \
    sh scripts/docker/pip_install_with_fallback.sh requirements/docker-vectorizer.txt

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
