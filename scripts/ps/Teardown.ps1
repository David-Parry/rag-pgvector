#requires -Version 5.1
<#
.SYNOPSIS
  Uninstall Helm release and optionally delete namespace (parallel to scripts/teardown.sh).

.NOTES
  Env: RELEASE, NAMESPACE, KEEP_NAMESPACE=1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$RELEASE = if ($env:RELEASE) { $env:RELEASE } else { 'rag' }
$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE } else { 'rag' }
$KEEP_NAMESPACE = if ($env:KEEP_NAMESPACE) { $env:KEEP_NAMESPACE } else { '0' }

Test-RagCommand helm 'Install Helm.'
Test-RagCommand kubectl 'Install kubectl.'

$stale = @(Get-RagAnyNamespacePortForwardInfo -Namespace $NAMESPACE)
if ($stale.Count -gt 0) {
    $ids = ($stale | ForEach-Object { $_.ProcessId }) -join ' '
    Write-Host "Killing kubectl port-forward processes targeting ${NAMESPACE}: $ids"
    Stop-RagProcessesGracefully -ProcessIds ($stale | ForEach-Object { [uint32]$_.ProcessId })
    Start-Sleep -Seconds 1
    $left = @(Get-RagAnyNamespacePortForwardInfo -Namespace $NAMESPACE)
    if ($left.Count -gt 0) {
        Stop-RagProcessesGracefully -ProcessIds ($left | ForEach-Object { [uint32]$_.ProcessId })
    }
}

helm status $RELEASE -n $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "helm uninstall ${RELEASE} -n ${NAMESPACE}"
    helm uninstall $RELEASE -n $NAMESPACE --wait --timeout 3m
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    Write-Host "helm release '${RELEASE}' not found in namespace '${NAMESPACE}' (skipping)"
}

kubectl get namespace $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    $pvcLines = @(kubectl -n $NAMESPACE get pvc -o name 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($pvcLines.Count -gt 0) {
        Write-Host "Deleting PVCs in ${NAMESPACE}:"
        foreach ($l in $pvcLines) {
            Write-Host "  $l"
        }
        & kubectl -n $NAMESPACE delete @pvcLines --wait=true --timeout=2m
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    else {
        Write-Host "No PVCs found in ${NAMESPACE}."
    }
}

if ($KEEP_NAMESPACE -eq '1') {
    Write-Host "KEEP_NAMESPACE=1 - leaving namespace '${NAMESPACE}' in place."
}
else {
    kubectl get namespace $NAMESPACE 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "kubectl delete namespace ${NAMESPACE}"
        kubectl delete namespace $NAMESPACE --wait=true --timeout=3m
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        for ($i = 1; $i -le 30; $i++) {
            kubectl get namespace $NAMESPACE 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                break
            }
            Write-Host "  waiting for namespace '${NAMESPACE}' to terminate..."
            Start-Sleep -Seconds 2
        }
        kubectl get namespace $NAMESPACE 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Error "WARNING: namespace '${NAMESPACE}' is still present (likely stuck on a finalizer)."
            kubectl get namespace $NAMESPACE -o yaml | Select-String -Pattern '(finalizers|^\s+- )' -Context 0, 5
            exit 1
        }
    }
    else {
        Write-Host "namespace '${NAMESPACE}' already gone."
    }
}

Write-Host ''
Write-Host 'Verification:'
kubectl get namespace $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  namespace '${NAMESPACE}' still present (KEEP_NAMESPACE=${KEEP_NAMESPACE}):"
    kubectl -n $NAMESPACE get all,pvc,secrets,configmaps 2>$null | ForEach-Object { Write-Host "    $_" }
}
else {
    Write-Host "  namespace '${NAMESPACE}' is gone."
}

helm status $RELEASE -n $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Error "WARNING: helm release '${RELEASE}' still reports as present."
    exit 1
}
else {
    Write-Host "  helm release '${RELEASE}' is gone."
}

Write-Host @"

Teardown complete.
Re-deploy with:
  .\scripts\ps\Docker-Desktop-Up.ps1
  .\scripts\ps\Helm-Install.ps1
"@
