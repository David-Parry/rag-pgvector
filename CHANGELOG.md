# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- PowerShell equivalents for repository helper scripts under `scripts/ps/`, including shared `_Common.ps1` (repo root, `.env` parsing, port-forward hygiene) and dispatcher `Rag.ps1` for common commands.

### Fixed

- `_Common.ps1`: stop using `$script:RagPsScriptsRoot` for repo-root discovery — dot-sourcing into a script invoked via `&` from `Rag.ps1` could leave that `$script:` slot unset on the dispatcher while StrictMode was on; use `$PSScriptRoot` / `$MyInvocation.MyCommand.Path` into a normal variable instead.

- PowerShell helpers: `kubectl get namespace …` probes no longer terminate when the namespace is missing — stderr from kubectl was treated as a terminating error under `$ErrorActionPreference = Stop` (notably PowerShell 7). Added `Invoke-RagKubectlProbe` for silent exit-code-only checks; used by `Docker-Desktop-Up.ps1` and `Helm-Install.ps1`.
