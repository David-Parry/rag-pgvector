# postgres-pgvector image

Vanilla `postgres:17` Debian image with the official PGDG `postgresql-17-pgvector` package installed via apt. Chosen for "enterprise realism" — we do not depend on the community `pgvector/pgvector` image.

## Build

```bash
docker build -t rag-pgvector/postgres:17 .
```

Docker Desktop's built-in Kubernetes shares the Docker daemon's image store, so a plain `docker build` is enough — no `push` or `load` step is needed before `helm install`.

## Local docker-compose smoke test

```bash
docker run --rm -p 5432:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  -v "$(pwd)/initdb:/docker-entrypoint-initdb.d:ro" \
  rag-pgvector/postgres:17
```

Then verify:

```bash
psql postgresql://rag:rag@localhost:5432/rag -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```
