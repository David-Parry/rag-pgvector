# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Docker build support for corporate PyPI mirrors: `vectorizer` and `question-api` builder stages accept optional BuildKit secrets (`uv_default_index`, `netrc`, `ssl_cert_bundle`), optional `UV_DEFAULT_INDEX` build-arg, and `scripts/docker-desktop-up.sh` / `scripts/ps/Docker-Desktop-Up.ps1` pass-through via `RAG_*` environment variables; documented in `documentation/DOCKER_PYPI_MIRROR.md`.

- PowerShell equivalents for repository helper scripts under `scripts/ps/`, including shared `_Common.ps1` (repo root, `.env` parsing, port-forward hygiene) and dispatcher `Rag.ps1` for common commands.

### Fixed

- `_Common.ps1`: stop using `$script:RagPsScriptsRoot` for repo-root discovery — dot-sourcing into a script invoked via `&` from `Rag.ps1` could leave that `$script:` slot unset on the dispatcher while StrictMode was on; use `$PSScriptRoot` / `$MyInvocation.MyCommand.Path` into a normal variable instead.

- PowerShell helpers: `kubectl get namespace …` probes no longer terminate when the namespace is missing — stderr from kubectl was treated as a terminating error under `$ErrorActionPreference = Stop` (notably PowerShell 7). Added `Invoke-RagKubectlProbe` for silent exit-code-only checks; used by `Docker-Desktop-Up.ps1` and `Helm-Install.ps1`.

- `scripts/ps/Port-Forward.ps1`: fix PowerShell 5.1 syntax error where `[int]` type cast was applied outside the if statement conditional. Moved type cast inside each branch to ensure compatibility with PowerShell 5.1.

- Docker builder: `UV_DEFAULT_INDEX` no longer left installs pulling wheels from `files.pythonhosted.org` — the builder rewrites `uv.lock` PyPI URLs to match the Artifactory (PEP 503) mirror when a default index is supplied (`scripts/docker/rewrite_uv_lock_for_mirror.py`). When the index URL embeds `user:token@`, `scripts/docker/prepare_artifactory_for_uv.py` merges them into `/root/.netrc` and strips userinfo from `UV_DEFAULT_INDEX` so artifact downloads authenticate. Builder images use `ghcr.io/astral-sh/uv:0.9.17` (was 0.5.7). Mirror builds default `UV_CONCURRENT_DOWNLOADS=2`. Builder shell trace (`set -x`) was removed so credentials in the index URL are less likely to appear in build logs.

- `vectorizer/Dockerfile`: header line used a hyphen instead of a comment; Docker treated it as an unknown instruction (`unknown instruction: -`).

- `scripts/docker/prepare_artifactory_for_uv.py`: repair corrupted imports (`Path` and `urllib.parse` were concatenated on one line), which caused a `SyntaxError` during the image builder and skipped mirror setup.

- `scripts/docker/rewrite_uv_lock_for_mirror.py`: fix Artifactory wheel URL path. JFrog Artifactory simple API is at `/api/pypi/<repo>/simple` but actual wheel files are served from `/<repo>/packages/...` (without the `/api/pypi/` prefix). The rewrite now strips `/api/pypi/` when present to generate correct file URLs.

### Changed

- `rag-core`: constrain `chonkie` to `>=1.6,<1.6.5` so dependency resolution avoids `chonkie` 1.6.5's `tokie` dependency (new wheels can be absent from corporate PyPI mirrors). `uv.lock` updated accordingly.

- `rag-core`: constrain `langchain-core` to `>=1.3.2,<1.4.0` to avoid uncached `langchain-core` 1.4.0 on corporate Artifactory mirrors. Version 1.3.x is more established and likely already cached. Users can relax this constraint once Artifactory is updated or when building without a mirror.

- `Test-RagCommand`: resolve `Application` commands first, try `name.exe` on Windows, and avoid `$IsWindows` (undefined on Windows PowerShell 5.1 under Strict Mode).
