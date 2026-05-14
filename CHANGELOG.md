# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `question-api` now exposes finalized Nova Sonic voice transcript events over `GET /voice/transcripts/{sessionId}` as a server-sent event stream, and `chat-bot-ui` renders those finalized voice transcript turns while a voice session is active.
- `chat-bot-ui` voice controls now show a live microphone input level meter while a WebRTC voice session is opening or connected.
- `scripts/ps/Check-NovaSonic.ps1` as a PowerShell equivalent of `scripts/check_nova_sonic.sh` for validating Nova Sonic STS identity, credential lifetime, and Bedrock model permission behavior on Windows.
- `question-api` Pipecat / AWS Bedrock Nova Sonic voice path with Small WebRTC routes (`/voice/start`, `/voice/api/offer` `POST` and `PATCH`), finalized transcript capture, and an `answer_question` tool bridge that delegates to the existing `AskService.ask()` RAG flow.
- `chat-bot-ui` voice interaction control and Next.js proxy routes for `question-api` Small WebRTC voice sessions, including streamed remote audio playback from Nova Sonic.
- `chat-bot-ui` browser voice permission prompt for microphone input and speaker output readiness before starting Nova Sonic voice chat.
- `chat-bot-ui` app-router error, global error, and not-found boundaries so runtime route failures render stable UI instead of triggering the Next development refresh fallback.
- Helm chart values for Nova Sonic-specific model and STS credential environment variables (`BEDROCK_NOVA_SONIC_MODEL_ID`, `SONIC_AWS_*`) so voice can use a separate Bedrock credential set from embeddings.
- Helm install helpers (`scripts/helm-install.sh`, `scripts/ps/Helm-Install.ps1`) now forward Nova Sonic model, role, temporary credentials, and voice runtime settings into the chart.
- `scripts/update-rag-pods.sh` and `scripts/ps/Update-RagPods.ps1` to rebuild images, run Helm upgrade, and rollout-restart existing RAG pods without teardown, namespace deletion, or PVC deletion.
- [documentation/QUESTION_API_VOICE.md](documentation/QUESTION_API_VOICE.md) documents voice configuration, Helm environment values, and manual Nova Sonic verification steps.
- `scripts/ps/Inspect-RedisCheckpoints.ps1` to scan Redis checkpoint keys and dump read-only values by Redis data type for local LangGraph checkpoint troubleshooting.
- `requirements/` directory: `requirements-dev.in` / `requirements-dev.txt` for local development, `docker-vectorizer.in` / `docker-vectorizer.txt` and `docker-question-api.in` / `docker-question-api.txt` for image installs; regenerate fully pinned files with `pip-compile` when needed.
- [documentation/PYTHON_PIP_WORKFLOW.md](documentation/PYTHON_PIP_WORKFLOW.md) summarizes venv setup, pip-tools, and optional `python -m build`.
- `scripts/docker/pip_install_with_fallback.sh` and `scripts/docker/prepare_artifactory_for_pip.py` for Docker `pip install` with optional mirror, `.netrc`, and TLS bundle; BuildKit secrets `pip_index_url` and optional `pip_config` (host `pip.ini` as `/etc/pip.conf` via `RAG_DOCKER_PIP_CONFIG_FILE`), plus env `RAG_PIP_INDEX_URL_FILE` / `RAG_DOCKER_PIP_INDEX_URL` (legacy `uv_default_index` / `RAG_UV_*` still supported).
- `scripts/ps/Check-KubernetesPods.ps1` and `.\Rag.ps1 check-pods` (aliases `pods-status`, `k8s-pods`) to verify pods in a namespace are **Running** and **Ready**; defaults kube context to **docker-desktop** (set `KUBE_CONTEXT=current` to skip switching).
- `scripts/ps/Restart-QuestionApi.ps1` and `.\Rag.ps1 restart-question-api` (aliases `restart-qa`, `restart-api`) to rollout-restart the question-api Kubernetes Deployment in the configured namespace.
- `question-api` **`POST /ask`** response field **`fromRedisSessionCache`** (default `false`; `true` when the consecutive-duplicate-question path reused the prior turn from Redis session checkpoint without pgvector or LLM). Chat UIs show a **Session cache (Redis)** chip when set.

- LangGraph-backed `POST /ask` in `question-api` with Redis checkpointing (`langgraph`, `langgraph-checkpoint-redis`): required JSON field `sessionId` (UUID) as `thread_id`, state channels `messages` and `aca_truth_turns`, and TTL settings `SESSION_CHECKPOINT_TTL_DAYS` / `SESSION_CHECKPOINT_TTL_REFRESH_ON_READ` plus `LANGGRAPH_REDIS_URL` or `REDIS_URL`.
- Helm chart support for an in-cluster **Redis Stack** deployment (`redisStack.enabled`, `redis/redis-stack-server`) and `question-api` defaults to the generated `rag-redis-stack` service for LangGraph checkpointing.
- Port-forward helpers (`scripts/ps/Port-Forward.ps1`, `scripts/port-forward.sh`) forward Redis Stack by default (`REDIS_PORT=6379`, `REDIS_SVC=rag-redis-stack`) and stale-forward cleanup recognizes the Redis service.
- `question_api/domain/ask_retrieval.py` for shared retrieval thresholding and citation shaping used by the graph.
- `chat-bot-ui`, `rag-pgvector/chat-bot-ui`, and `rag-pgvector-chat` now send and validate `sessionId` on `/api/chat` before proxying to `question-api`.
- `scripts/ask.sh` generates or accepts `SESSION_ID` and includes `sessionId` in the `/ask` body.
- Documentation: [SESSION_LANGGRAPH_REDIS.md](documentation/SESSION_LANGGRAPH_REDIS.md).
- `evals/` workspace member with a DeepEval retriever benchmark for sweeping pgvector `top_k` and cosine-distance thresholds against `BILLS-115hr1625enr` goldens.
- `scripts/eval-retrieval.sh` CLI runner plus unit and opt-in integration tests for retriever benchmark coverage.

### Removed

- `uv.lock`, `uv-install.ps1`, and uv-specific Docker scripts: `uv_sync_with_fallback.sh`, `prepare_artifactory_for_uv.py`, `rewrite_uv_lock_for_mirror.py`, `rewrite_uv_lock_for_public_pypi.py`, `check_uv_lock_artifact_access.py`.

### Changed

- `chat-bot-ui` voice responses now guard JSON parsing so HTML proxy or route errors surface as readable voice API failures instead of `Unexpected token '<'` parse exceptions.
- Local Helm voice deployment now defaults `VOICE_ENABLED` to `true`, and `/voice/start` also rejects disabled deployments so the UI reports voice availability before WebRTC offer negotiation.
- `chat-bot-ui` voice WebRTC calls now use browser-side `NEXT_PUBLIC_RAG_QUESTION_API_URL` with a `http://localhost:8000` default, and `question-api` allows local chat UI origins through CORS for direct voice endpoint access.
- Local question-api forwarding and chat defaults now use `localhost:8000` instead of `localhost:8002` so text and voice clients target the same backend port.
- Docker requirement files **`requirements/docker-vectorizer.txt`** and **`requirements/docker-question-api.txt`** install **`-e ./libs/rag-core`** before the app package; **`vectorizer`** and **`question-api`** depend on **`rag-core==0.1.0`** instead of **`rag-core @ file:../libs/rag-core`** so pip does not resolve the path dependency to **`/libs/rag-core`** inside the Linux builder.
- **Python tooling:** Astral **uv** and **`uv_build`** are replaced by **pip** (PyPI), **`setuptools.build_meta`**, and workspace installs from **`requirements/*.txt`**. Docker images no longer copy `ghcr.io/astral-sh/uv`; they create a venv and `pip install -r` the service requirement file. Host and CI workflows use `python -m venv .venv` and `pip install -r requirements/requirements-dev.txt`; optional **`python -m build`** (PyPA `build` package) produces sdists/wheels per package `[build-system]`.
- `scripts/ps/env_var_artifactory.ps1` populates **`RAG_DOCKER_PIP_INDEX_URL`** (and optional one-line **`RAG_PIP_INDEX_URL_FILE`**) when using **`RAG_DOCKER_PIP_CONFIG_FILE`** / discovered `pip.ini`, with more permissive **`index-url`** parsing (quotes, comments, `%ProgramData%\pip\pip.ini` candidate).
- `scripts/ps/Helm-Install.ps1` imports `.env` before resolving release settings, preserves current session values created by helper scripts, maps local Redis URLs (`localhost`, `127.0.0.1`, `host.docker.internal`) to the Helm-installed `redis://rag-redis-stack:6379` service, and forwards runtime Redis/checkpoint/retrieval variables (`LANGGRAPH_REDIS_URL`, `SESSION_CHECKPOINT_*`, `RETRIEVAL_*`) into Helm values so pods do not fall back to localhost defaults.
- `scripts/eval-retrieval.sh` and `scripts/ps/Eval-Retrieval.ps1` invoke the repo `.venv` Python instead of `uv run`.
- Root `pyproject.toml` no longer declares `[tool.uv.workspace]` or `[tool.uv.sources]`; dev dependencies are listed in `requirements/requirements-dev.in`.
- PowerShell and bash helpers: namespace existence checks use discarded kubectl output (`Test-RagKubernetesNamespaceExists` / `>/dev/null 2>&1`) so a **removed** or missing namespace does not spam the console; `Port-Forward.ps1` / `port-forward.sh` exit early if the namespace is absent.

- `AskService` now invokes a compiled LangGraph instead of an inline retrieve-orchestration only.
- `question-api`: structured logs `ask.langgraph_checkpoint_read` and `ask.langgraph_checkpoint_write` expose `thread_id`, prior/final message and ACA turn counts, and clarify that session state is loaded through the LangGraph checkpointer (for example Redis). When the new user text matches the **immediately previous** user message in the same session (whitespace- and case-normalized), `ask_graph.duplicate_consecutive_question` is emitted and **pgvector similarity search and LLM generation are skipped** for that turn; the graph still completes one step so the checkpointer is updated.
- `question-api`: `GET /healthz` includes `sessionMemory` (Redis backend and sanitized endpoint) when the app container is initialized. Startup log `question_api.langgraph_session_memory` and per-ask / per-node logs (`session_memory_backend`, `session_memory_endpoint`, `ask_graph.session_messages_for_context`, `session_memory_serves_context` on checkpoint events) make it explicit when Redis backs merged chat context.
- [SESSION_LANGGRAPH_REDIS.md](documentation/SESSION_LANGGRAPH_REDIS.md): inspecting Redis keys; verifying Redis for merged context; `sanitize_redis_url_for_log` for safe log and health fields.

- `scripts/eval-retrieval.sh` now writes a timestamped markdown report under `documentation/eval-reports/` while still printing benchmark output to the terminal.

- `scripts/ps/Eval-Retrieval.ps1` PowerShell runner for the DeepEval retriever benchmark report, available through `scripts/ps/Rag.ps1 eval-retrieval`.

- DeepEval report runners now explicitly require an already-running pgvector database and fail fast when `DATABASE_URL` is unreachable, without starting or tearing down database resources.

- DeepEval report runners now load `ANTHROPIC_API_KEY` from `ANTHROPIC_API_KEY_FILE` or `claudeapi.txt` when the environment variable is not set.

- DeepEval report runners default to `INFO` logging via `DEEPEVAL_LOG_LEVEL` and keep stderr debug output out of successful markdown reports.

- DeepEval reports now include configurable pass/fail gates and a summary section for multi-threshold retrieval sweeps.

- DeepEval report runners now write progress and third-party SDK output to a companion `.log` file so generated markdown reports remain previewable.

- `DEEPEVAL_VERBOSE_MODE` now controls DeepEval metric display verbosity and defaults off for clean report runs.

- DeepEval report runners support `DEEPEVAL_REPORT_FILE_TYPE=html` for generated HTML summary reports.

- Generated DeepEval report files under `documentation/eval-reports/` are ignored to avoid accidentally committing SDK request metadata.

- `.gitattributes` keeps shell scripts checked out with LF line endings so bash runners work consistently on Windows.

- Direct Anthropic Claude provider support for `question-api`, configured by `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE`.

- Docker build support for corporate PyPI mirrors: `vectorizer` and `question-api` builder stages accept optional BuildKit secrets (`uv_default_index`, `netrc`, `ssl_cert_bundle`), optional `UV_DEFAULT_INDEX` build-arg, and `scripts/docker-desktop-up.sh` / `scripts/ps/Docker-Desktop-Up.ps1` pass-through via `RAG_*` environment variables; documented in `documentation/DOCKER_PYPI_MIRROR.md`.

- PowerShell equivalents for repository helper scripts under `scripts/ps/`, including shared `_Common.ps1` (repo root, `.env` parsing, port-forward hygiene) and dispatcher `Rag.ps1` for common commands.

### Fixed

- `scripts/ps/Check-NovaSonic.ps1` now maps `SONIC_AWS_*` credentials from `.env` into the AWS CLI environment and clears profile fallback so checks run against the Nova Sonic federated identity, not the developer's default account.
- `scripts/ps/Check-NovaSonic.ps1` suppresses expected Bedrock probe error details on successful Nova Sonic access checks by default, with `-ShowAwsError` available for raw AWS diagnostics.
- `scripts/ps/Check-NovaSonic.ps1` now captures AWS CLI probe stderr without PowerShell converting expected Bedrock errors into terminating `NativeCommandError` failures.
- `scripts/ps/Docker-Desktop-Up.ps1` now exits with a non-zero status when a `docker build` step fails (previously it could still print “Cluster ready” after a failed image build).

- `question-api`: consecutive duplicate-question reuse (and UI `fromRedisSessionCache` flag) did not trigger when prior checkpoint messages were deserialized from Redis as plain dicts; duplicate detection and last-reply parsing now use normalized message roles and ACA `from_redis_session_cache` instead of strict `isinstance(HumanMessage)` / `AIMessage` only. **Also** handles LangChain **JsonPlus `lc` / `constructor`** message blobs (root `type` is `constructor`, not `human` / `ai`).

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

- Docker builder: `UV_DEFAULT_INDEX` no longer left installs pulling wheels from `files.pythonhosted.org` — the builder rewrites `uv.lock` PyPI URLs to match the Artifactory (PEP 503) mirror when a default index is supplied (`scripts/docker/rewrite_uv_lock_for_mirror.py`). When the index URL embeds `user:token@`, `scripts/docker/prepare_artifactory_for_uv.py` merges them into `/root/.netrc` and strips userinfo from `UV_DEFAULT_INDEX` so artifact downloads authenticate. Builder images use `ghcr.io/astral-sh/uv:0.11.14` (was 0.5.7, then 0.9.17). Mirror builds default `UV_CONCURRENT_DOWNLOADS=2`. Builder shell trace (`set -x`) was removed so credentials in the index URL are less likely to appear in build logs.

- `vectorizer/Dockerfile`: header line used a hyphen instead of a comment; Docker treated it as an unknown instruction (`unknown instruction: -`).

- `scripts/docker/prepare_artifactory_for_uv.py`: repair corrupted imports (`Path` and `urllib.parse` were concatenated on one line), which caused a `SyntaxError` during the image builder and skipped mirror setup.

- `scripts/docker/rewrite_uv_lock_for_mirror.py`: fix Artifactory wheel URL path. JFrog Artifactory simple API is at `/api/pypi/<repo>/simple` but actual wheel files are served from `/<repo>/packages/...` (without the `/api/pypi/` prefix). The rewrite now strips `/api/pypi/` when present to generate correct file URLs.

### Changed

- Workspace members (`libs/rag-core`, `vectorizer`, `question-api`, `evals`) use the Astral `uv_build` PEP 517 backend instead of `hatchling`; the `uv` binary supplies a compatible build implementation so image builds do not need `hatchling` on the PyPI mirror. `vectorizer/Dockerfile` and `question-api/Dockerfile` copy `ghcr.io/astral-sh/uv:0.11.14` (replacing `0.9.17`).

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
