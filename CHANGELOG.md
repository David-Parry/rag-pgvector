# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `evals/` workspace member with a DeepEval retriever benchmark for sweeping pgvector `top_k` and cosine-distance thresholds against `BILLS-115hr1625enr` goldens.

- `scripts/eval-retrieval.sh` CLI runner plus unit and opt-in integration tests for retriever benchmark coverage.

- `scripts/eval-retrieval.sh` now writes a timestamped markdown report under root-level `dist/` while still printing benchmark output to the terminal.

- `scripts/ps/Eval-Retrieval.ps1` PowerShell runner for the DeepEval retriever benchmark report, available through `scripts/ps/Rag.ps1 eval-retrieval`.

- DeepEval report runners now explicitly require an already-running pgvector database and fail fast when `DATABASE_URL` is unreachable, without starting or tearing down database resources.

- DeepEval report runners now load `ANTHROPIC_API_KEY` from `ANTHROPIC_API_KEY_FILE` or `claudeapi.txt` when the environment variable is not set.

- DeepEval report runners default to `INFO` logging via `DEEPEVAL_LOG_LEVEL` and keep stderr debug output out of successful markdown reports.

- DeepEval reports now include configurable pass/fail gates and a summary section for multi-threshold retrieval sweeps.

- DeepEval report runners now write progress and third-party SDK output to a companion `.log` file so generated markdown reports remain previewable.

- `DEEPEVAL_VERBOSE_MODE` now controls DeepEval metric display verbosity and defaults off for clean report runs.

- DeepEval report runners support `DEEPEVAL_REPORT_FILE_TYPE=html` for generated HTML summary reports.

- Generated DeepEval report files under root-level `dist/` are ignored to avoid accidentally committing SDK request metadata.

- `.gitattributes` keeps shell scripts checked out with LF line endings so bash runners work consistently on Windows.

- Direct Anthropic Claude provider support for `question-api`, configured by `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE`.

- Docker build support for corporate PyPI mirrors: `vectorizer` and `question-api` builder stages accept optional BuildKit secrets (`uv_default_index`, `netrc`, `ssl_cert_bundle`), optional `UV_DEFAULT_INDEX` build-arg, and `scripts/docker-desktop-up.sh` / `scripts/ps/Docker-Desktop-Up.ps1` pass-through via `RAG_*` environment variables; documented in `documentation/DOCKER_PYPI_MIRROR.md`.

- PowerShell equivalents for repository helper scripts under `scripts/ps/`, including shared `_Common.ps1` (repo root, `.env` parsing, port-forward hygiene) and dispatcher `Rag.ps1` for common commands.

### Fixed

- `rag-core`: parse DeepEval grid settings from comma-separated environment values before pydantic-settings attempts JSON decoding; pytest now configures repo source and test-helper paths without requiring a manual `PYTHONPATH`.

- Tests: isolate the Anthropic missing-key unit test from real shell credentials and run eval integration tests with a psycopg-compatible selector event loop on Windows.

- Tests: exclude integration-marked tests from the default pytest run so external Bedrock, Anthropic, and pgvector checks remain opt-in via `pytest -m integration`.

- `rag-evals`: configure the CLI to use a Windows Selector event loop before opening async psycopg connections, matching the integration test policy.

- `rag-evals`: emit progress logs for benchmark start, retrieval per golden, scoring per grid cell, and DeepEval metric case completion so long judge runs no longer appear stalled.

- PowerShell helpers now prepend `%USERPROFILE%\.local\bin` to the process PATH at startup so locally installed tools such as `uv` are discovered consistently.

- `question-api`: log the configured Anthropic model during startup instead of referencing the removed `llm_provider` setting.

- `scripts/ps/Ingest-Package.ps1`: build request JSON with native PowerShell parsing instead of `jq --argjson`, preventing Windows PowerShell from stripping metadata JSON quotes before invoking `jq`.

- `scripts/ps/Ask.ps1`: remove the unnecessary `jq` dependency by using native PowerShell JSON formatting for request previews and raw responses.

- `scripts/ps/Ask.ps1`: quote PowerShell `jq` arguments so JSON metadata is passed correctly to `jq --argjson`.

- `_Common.ps1`: stop using `$script:RagPsScriptsRoot` for repo-root discovery — dot-sourcing into a script invoked via `&` from `Rag.ps1` could leave that `$script:` slot unset on the dispatcher while StrictMode was on; use `$PSScriptRoot` / `$MyInvocation.MyCommand.Path` into a normal variable instead.

- PowerShell helpers: `kubectl get namespace …` probes no longer terminate when the namespace is missing — stderr from kubectl was treated as a terminating error under `$ErrorActionPreference = Stop` (notably PowerShell 7). Added `Invoke-RagKubectlProbe` for silent exit-code-only checks; used by `Docker-Desktop-Up.ps1` and `Helm-Install.ps1`.

- `scripts/ps/Helm-Install.ps1`: avoid printing secret-bearing `--set-string` arguments to terminal logs, and stop after Helm failures instead of printing a success message.

- `scripts/ps/Docker-Desktop-Up.ps1`: import locally built images into Docker Desktop Kubernetes' `containerd` image namespace when the cluster uses a containerd runtime, preventing local images from being pulled from Docker Hub.

- `scripts/ps/Port-Forward.ps1`: fix PowerShell 5.1 syntax error where `[int]` type cast was applied outside the if statement conditional. Moved type cast inside each branch to ensure compatibility with PowerShell 5.1.

- `scripts/ps/env_var_artifactory.ps1`: resolve the repo `.env` from the project root, create `RAG_UV_DEFAULT_INDEX_FILE` from the configured Artifactory `pip.ini` index when needed, and invoke `Docker-Desktop-Up.ps1` directly so Docker builds receive the PyPI mirror secret.

- Docker builder: `UV_DEFAULT_INDEX` no longer left installs pulling wheels from `files.pythonhosted.org` — the builder rewrites `uv.lock` PyPI URLs to match the Artifactory (PEP 503) mirror when a default index is supplied (`scripts/docker/rewrite_uv_lock_for_mirror.py`). When the index URL embeds `user:token@`, `scripts/docker/prepare_artifactory_for_uv.py` merges them into `/root/.netrc` and strips userinfo from `UV_DEFAULT_INDEX` so artifact downloads authenticate. Builder images use `ghcr.io/astral-sh/uv:0.9.17` (was 0.5.7). Mirror builds default `UV_CONCURRENT_DOWNLOADS=2`. Builder shell trace (`set -x`) was removed so credentials in the index URL are less likely to appear in build logs.

- `vectorizer/Dockerfile`: header line used a hyphen instead of a comment; Docker treated it as an unknown instruction (`unknown instruction: -`).

- `scripts/docker/prepare_artifactory_for_uv.py`: repair corrupted imports (`Path` and `urllib.parse` were concatenated on one line), which caused a `SyntaxError` during the image builder and skipped mirror setup.

- `scripts/docker/rewrite_uv_lock_for_mirror.py`: fix Artifactory wheel URL path. JFrog Artifactory simple API is at `/api/pypi/<repo>/simple` but actual wheel files are served from `/<repo>/packages/...` (without the `/api/pypi/` prefix). The rewrite now strips `/api/pypi/` when present to generate correct file URLs.

### Changed

- `evals`: expanded and grounded the `BILLS-115hr1625enr` benchmark goldens in the official govinfo PDF text, with 50 questions covering sections 7036-7041, UNRWA provisions, and sections 1002-1007.

- Simplified `question-api` LLM composition to direct Anthropic Claude only and removed the Bedrock Claude fallback wiring.

- Restored embeddings to the previous direct Bedrock credential path because Anthropic does not provide embeddings.

- Updated Helm and environment examples to use direct Anthropic settings for answer generation while keeping embedding settings separate.

- Added local AWS profile/session support for Docker Desktop Helm installs by exporting temporary AWS credentials, including `AWS_SESSION_TOKEN`, for embedding access while keeping the embedding bearer token separate.

### Removed

- Removed Bedrock Claude Secrets Manager and STS-assumed-role runtime support, Helm values, scripts documentation, and tests.

- `rag-core`: constrain `chonkie` to `>=1.6,<1.6.5` so dependency resolution avoids `chonkie` 1.6.5's `tokie` dependency (new wheels can be absent from corporate PyPI mirrors). `uv.lock` updated accordingly.

- `rag-core`: constrain `langchain-core` to `>=1.3.2,<1.4.0` to avoid uncached `langchain-core` 1.4.0 on corporate Artifactory mirrors. Version 1.3.x is more established and likely already cached. Users can relax this constraint once Artifactory is updated or when building without a mirror.

- `Test-RagCommand`: resolve `Application` commands first, try `name.exe` on Windows, and avoid `$IsWindows` (undefined on Windows PowerShell 5.1 under Strict Mode).
