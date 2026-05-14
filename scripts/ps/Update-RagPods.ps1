#requires -Version 5.1
<#
.SYNOPSIS
  Update existing rag-pgvector Kubernetes pods without teardown.

.DESCRIPTION
  Rebuilds local images, runs Helm upgrade in place, then rollout-restarts the
  selected application Deployments so same-tag local images and updated secrets
  are picked up. This does not uninstall Helm, delete PVCs, or delete the
  namespace.

.NOTES
  Env:
    NAMESPACE           default rag
    RELEASE             default rag
    TAG                 default 0.1.0
    KUBE_CONTEXT        passed through to Docker-Desktop-Up.ps1 / kubectl
    ROLLOUT_TIMEOUT     default 300s
    UPDATE_COMPONENTS   comma-separated deployment components, default question-api
    UPDATE_SKIP_BUILD   1 to skip Docker image rebuild/import
    UPDATE_SKIP_HELM    1 to skip Helm upgrade
    UPDATE_SKIP_ROLLOUT 1 to skip rollout restart
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

function Test-RagTruthy {
    param([string]$Value)
    return $Value -match '^(1|true|yes|on)$'
}

function Get-RagUpdateComponents {
    $raw = if ($env:UPDATE_COMPONENTS) { $env:UPDATE_COMPONENTS } else { 'question-api' }
    return @(
        $raw -split ',' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
}

function Restart-RagComponentDeployment {
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$Component,
        [Parameter(Mandatory)][string]$Timeout
    )

    $label = "app.kubernetes.io/component=$Component"
    $raw = kubectl get deploy -n $Namespace -l $label -o json 2>$null
    if (-not $raw) {
        Write-Warning "No Deployment found for component '$Component' in namespace '$Namespace'."
        return
    }

    $json = $raw | ConvertFrom-Json
    $items = @($json.items)
    if ($items.Count -eq 0) {
        Write-Warning "No Deployment found for component '$Component' in namespace '$Namespace'."
        return
    }

    foreach ($item in $items) {
        $name = [string]$item.metadata.name
        Write-Host "Rolling deployment/$name in namespace $Namespace ..."
        kubectl rollout restart "deployment/$name" -n $Namespace
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        kubectl rollout status "deployment/$name" -n $Namespace "--timeout=$Timeout"
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}

$ROOT_DIR = Get-RagRepoRoot
Set-Location $ROOT_DIR

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE.Trim() } else { 'rag' }
$RELEASE = if ($env:RELEASE) { $env:RELEASE.Trim() } else { 'rag' }
$TIMEOUT = if ($env:ROLLOUT_TIMEOUT) { $env:ROLLOUT_TIMEOUT.Trim() } else { '300s' }
$components = Get-RagUpdateComponents

Write-Host @"
Updating rag-pgvector pods in place.
  release:    $RELEASE
  namespace:  $NAMESPACE
  components: $($components -join ', ')

This does NOT run teardown, uninstall Helm, delete PVCs, or delete the namespace.
"@

if (-not (Test-RagTruthy $env:UPDATE_SKIP_BUILD)) {
    Write-Host ''
    Write-Host 'Step 1/3: build/import local images'
    & (Join-Path $PSScriptRoot 'Docker-Desktop-Up.ps1')
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    Write-Host 'Step 1/3: skipped image build/import (UPDATE_SKIP_BUILD=1)'
}

if (-not (Test-RagTruthy $env:UPDATE_SKIP_HELM)) {
    Write-Host ''
    Write-Host 'Step 2/3: helm upgrade existing release'
    & (Join-Path $PSScriptRoot 'Helm-Install.ps1')
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    Write-Host 'Step 2/3: skipped Helm upgrade (UPDATE_SKIP_HELM=1)'
}

if (-not (Test-RagTruthy $env:UPDATE_SKIP_ROLLOUT)) {
    Write-Host ''
    Write-Host 'Step 3/3: rollout restart updated Deployment(s)'
    Test-RagCommand kubectl 'Install kubectl (winget install Kubernetes.kubectl).'
    if ($env:KUBE_CONTEXT -and $env:KUBE_CONTEXT.Trim() -ine 'current') {
        kubectl config use-context $env:KUBE_CONTEXT.Trim() | Out-Null
    }
    if (-not (Test-RagKubernetesNamespaceExists -Namespace $NAMESPACE)) {
        Write-Error "Namespace '$NAMESPACE' does not exist after Helm upgrade."
        exit 1
    }
    foreach ($component in $components) {
        Restart-RagComponentDeployment -Namespace $NAMESPACE -Component $component -Timeout $TIMEOUT
    }
}
else {
    Write-Host 'Step 3/3: skipped rollout restart (UPDATE_SKIP_ROLLOUT=1)'
}

Write-Host ''
Write-Host 'Update complete. Current pods:'
kubectl get pods -n $NAMESPACE -o wide
