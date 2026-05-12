-- Run once on first cluster init (postgres image entrypoint).
-- Loaded into the chart via a ConfigMap mounted at /docker-entrypoint-initdb.d/.
CREATE EXTENSION IF NOT EXISTS vector;
