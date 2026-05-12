#requires -Version 5.1
<#
.SYNOPSIS
  Verify Docker Desktop Kubernetes is reachable and build local images.

.DESCRIPTION
  Parallel to scripts/docker-desktop-up.sh — Docker Desktop shares the daemon
  with Kubernetes; plain docker build is enough.

.NOTES
  Enable Kubernetes in Docker Desktop before running.

.EXAMPLE
  .\Docker-Desktop-Up.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE } else { 'rag' }
$TAG = if ($env:TAG) { $env:TAG } else { '0.1.0' }
$KUBE_CONTEXT = if ($env:KUBE_CONTEXT) { $env:KUBE_CONTEXT } else { 'docker-desktop' }

$ROOT_DIR = Get-RagRepoRoot
Set-Location $ROOT_DIR

Test-RagCommand docker 'Install Docker Desktop for Windows.'
Test-RagCommand kubectl 'Install kubectl (winget install Kubernetes.kubectl).'

Write-Host 'Checking Docker Desktop Kubernetes context...'
$contextNames = @(kubectl config get-contexts -o name 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($contextNames -notcontains $KUBE_CONTEXT) {
    Write-Error @"
ERROR: kube context '$KUBE_CONTEXT' was not found.

Enable Kubernetes in Docker Desktop:
  Docker Desktop -> Settings -> Kubernetes -> Enable Kubernetes -> Apply & restart

Then re-run this script.
"@
    exit 1
}

kubectl config use-context $KUBE_CONTEXT | Out-Null

if ((Invoke-RagKubectlProbe -Arguments @('version', '--request-timeout=5s')) -ne 0) {
    Write-Error "ERROR: cannot reach the '$KUBE_CONTEXT' API server. Is Docker Desktop running?"
    exit 1
}

if ((Invoke-RagKubectlProbe -Arguments @('get', 'namespace', $NAMESPACE)) -ne 0) {
    kubectl create namespace $NAMESPACE
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

# Optional corporate PyPI / TLS — see documentation/DOCKER_PYPI_MIRROR.md
$pyAppBuildArgs = @()
if ($env:RAG_DOCKER_UV_DEFAULT_INDEX) {
    $pyAppBuildArgs += '--build-arg', "UV_DEFAULT_INDEX=$($env:RAG_DOCKER_UV_DEFAULT_INDEX)"
}
if ($env:RAG_UV_DEFAULT_INDEX_FILE) {
    $pyAppBuildArgs += '--secret', "id=uv_default_index,src=$($env:RAG_UV_DEFAULT_INDEX_FILE)"
}
if ($env:RAG_DOCKER_NETRC_FILE) {
    $pyAppBuildArgs += '--secret', "id=netrc,src=$($env:RAG_DOCKER_NETRC_FILE)"
}
if ($env:RAG_DOCKER_SSL_CERT_BUNDLE_FILE) {
    $pyAppBuildArgs += '--secret', "id=ssl_cert_bundle,src=$($env:RAG_DOCKER_SSL_CERT_BUNDLE_FILE)"
}

Write-Host ''
Write-Host 'Building rag-pgvector/postgres:17 ...'
docker build -t 'rag-pgvector/postgres:17' (Join-Path $ROOT_DIR 'infra/docker/postgres-pgvector')

Write-Host ''
Write-Host "Building rag-pgvector/vectorizer:${TAG} ..."
docker build @pyAppBuildArgs -t "rag-pgvector/vectorizer:${TAG}" -f (Join-Path $ROOT_DIR 'vectorizer/Dockerfile') $ROOT_DIR

Write-Host ''
Write-Host "Building rag-pgvector/question-api:${TAG} ..."
docker build @pyAppBuildArgs -t "rag-pgvector/question-api:${TAG}" -f (Join-Path $ROOT_DIR 'question-api/Dockerfile') $ROOT_DIR

Write-Host @"

Cluster ready (Docker Desktop Kubernetes).
  context:    $KUBE_CONTEXT
  namespace:  $NAMESPACE
  images:     rag-pgvector/postgres:17, rag-pgvector/vectorizer:${TAG}, rag-pgvector/question-api:${TAG}

Docker Desktop Kubernetes shares the Docker daemon, so these images are visible
to the cluster without any push or load step.

Next: .\scripts\ps\Helm-Install.ps1   or   .\scripts\ps\Rag.ps1 helm-install
"@
