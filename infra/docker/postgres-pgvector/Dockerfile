# Vanilla postgres:17 with pgvector installed via the official PGDG apt package.
# This is the explicit "enterprise realism" path: we do NOT use pgvector/pgvector:pg17.
#
# Build:
#   docker build -t rag-pgvector/postgres:17 infra/docker/postgres-pgvector/
#
# Docker Desktop's built-in Kubernetes shares the Docker daemon, so this image
# is visible to the cluster immediately after build. No registry push or
# `kubectl load` step is required.

FROM postgres:17

ARG PGVECTOR_PACKAGE=postgresql-17-pgvector

RUN apt-get update \
 && apt-get install -y --no-install-recommends ${PGVECTOR_PACKAGE} \
 && rm -rf /var/lib/apt/lists/*

# postgres:17 already exposes 5432 and uses the standard entrypoint; we only
# need pgvector. The CREATE EXTENSION call lives in an initdb script supplied
# by the Helm chart (mounted from a ConfigMap into /docker-entrypoint-initdb.d).
