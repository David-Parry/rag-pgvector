#requires -Version 5.1
<#
.SYNOPSIS
  Restart the question-api Kubernetes Deployment (kubectl rollout restart + rollout status).

.DESCRIPTION
  Finds the Deployment labeled app.kubernetes.io/component=question-api in the target
  namespace (default rag), matching the Helm chart in infra/helm/rag-pgvector.

  Requires kubectl and a reachable cluster (e.g. Docker Desktop Kubernetes). Rebuild the
  image first if you need new Python code: .\Rag.ps1 docker-up then upgrade the release.

.EXAMPLE
  .\Restart-QuestionApi.ps1

.EXAMPLE
  $env:NAMESPACE = 'rag'; $env:KUBE_CONTEXT = 'docker-desktop'; .\Restart-QuestionApi.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE.Trim() } else { 'rag' }
$TIMEOUT = if ($env:ROLLOUT_TIMEOUT) { $env:ROLLOUT_TIMEOUT.Trim() } else { '300s' }

Test-RagCommand kubectl 'Install kubectl (winget install Kubernetes.kubectl).'

if ($env:KUBE_CONTEXT) {
    kubectl config use-context $env:KUBE_CONTEXT.Trim() | Out-Null
}

$label = 'app.kubernetes.io/component=question-api'
$raw = kubectl get deploy -n $NAMESPACE -l $label -o json 2>$null
if (-not $raw) {
    Write-Error "kubectl get deploy failed for namespace '$NAMESPACE'. Is the cluster reachable?"
}

$json = $raw | ConvertFrom-Json
if (-not $json.items -or @($json.items).Count -eq 0) {
    Write-Error @"
No Deployment with label $label in namespace '$NAMESPACE'.

Install the chart first: .\Rag.ps1 helm-install
Ensure question-api is enabled (qa.enabled) in your Helm values.
"@
}

$items = @($json.items)
if ($items.Count -gt 1) {
    Write-Warning "Multiple question-api deployments matched ($($items.Count)); restarting the first: $($items[0].metadata.name)"
}

$name = [string]$items[0].metadata.name
Write-Host "Restarting deployment/$name in namespace $NAMESPACE ..."
kubectl rollout restart "deployment/$name" -n $NAMESPACE
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Waiting for rollout (timeout $TIMEOUT) ..."
kubectl rollout status "deployment/$name" -n $NAMESPACE "--timeout=$TIMEOUT"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "question-api restarted: deployment/$name"
