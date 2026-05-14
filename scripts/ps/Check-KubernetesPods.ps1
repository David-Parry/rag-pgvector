#requires -Version 5.1
<#
.SYNOPSIS
  Verify Kubernetes pods are Running and Ready (defaults to Docker Desktop context).

.DESCRIPTION
  Targets the cluster kubectl is configured for—by default switches to kube context
  ``docker-desktop`` (Docker Desktop Kubernetes). Lists pods in the namespace and exits
  non-zero if any pod is not phase Running or does not report Ready=True.

.NOTES
  Environment:
    NAMESPACE          Kubernetes namespace (default: rag)
    KUBE_CONTEXT       Context name to select before checks (default: docker-desktop).
                       Set to ``current`` to keep whatever context is already active.
    POD_LABEL_SELECTOR Optional ``kubectl -l`` selector (e.g. app.kubernetes.io/instance=rag)

.EXAMPLE
  .\Check-KubernetesPods.ps1

.EXAMPLE
  $env:NAMESPACE = 'rag'; $env:KUBE_CONTEXT = 'current'; .\Check-KubernetesPods.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

Test-RagCommand kubectl 'Install kubectl (winget install Kubernetes.kubectl).'

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE.Trim() } else { 'rag' }
$KUBE_CONTEXT = if ($null -ne $env:KUBE_CONTEXT) { $env:KUBE_CONTEXT.Trim() } else { 'docker-desktop' }
$LABEL = if ($env:POD_LABEL_SELECTOR) { $env:POD_LABEL_SELECTOR.Trim() } else { '' }

if ((Invoke-RagKubectlProbe -Arguments @('version', '--request-timeout=5s')) -ne 0) {
    Write-Error 'Cannot reach the Kubernetes API server. Is Docker Desktop (Kubernetes) running?'
    exit 2
}

if ($KUBE_CONTEXT -and ($KUBE_CONTEXT -ine 'current')) {
    $names = @(kubectl config get-contexts -o name 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($names -contains $KUBE_CONTEXT) {
        kubectl config use-context $KUBE_CONTEXT | Out-Null
        Write-Host "Using kube context: $KUBE_CONTEXT"
    }
    else {
        Write-Warning "Kube context '$KUBE_CONTEXT' not found; leaving current: $(kubectl config current-context 2>$null)"
    }
}
else {
    Write-Host "Using kube context (unchanged): $(kubectl config current-context 2>$null)"
}

if (-not (Test-RagKubernetesNamespaceExists -Namespace $NAMESPACE)) {
    Write-Error "Namespace '$NAMESPACE' does not exist or cannot be read."
    exit 2
}

$selectorArgs = @()
if ($LABEL) {
    $selectorArgs = @('-l', $LABEL)
}

$outFile = [System.IO.Path]::GetTempFileName()
$errFile = [System.IO.Path]::GetTempFileName()
try {
    $kc = (Get-Command kubectl -CommandType Application -ErrorAction Stop).Source
    $argsList = @('get', 'pods', '-n', $NAMESPACE) + $selectorArgs + @('-o', 'json')
    $p = Start-Process -FilePath $kc -ArgumentList $argsList -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    if ($p.ExitCode -ne 0) {
        $stderr = if (Test-Path $errFile) { Get-Content -LiteralPath $errFile -Raw } else { '' }
        Write-Error "kubectl get pods failed: $stderr"
        exit $p.ExitCode
    }
    $doc = Get-Content -LiteralPath $outFile -Raw | ConvertFrom-Json
}
finally {
    Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host "Pods in namespace '$NAMESPACE'$(if ($LABEL) { " (selector: $LABEL)" } else { '' }):"
kubectl get pods -n $NAMESPACE @selectorArgs -o wide
Write-Host ''

$items = @($doc.items)
if ($items.Count -eq 0) {
    Write-Warning 'No pods matched the query.'
    exit 1
}

function Get-RagJsonProperty {
    param(
        [Parameter(Mandatory = $true)] [object] $Object,
        [Parameter(Mandatory = $true)] [string] $Name
    )
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

$failures = [System.Collections.Generic.List[string]]::new()
foreach ($pod in $items) {
    $name = [string](Get-RagJsonProperty -Object $pod.metadata -Name 'name')
    $phase = [string](Get-RagJsonProperty -Object $pod.status -Name 'phase')
    $conditions = @(Get-RagJsonProperty -Object $pod.status -Name 'conditions')
    $readyCond = $conditions | Where-Object { $_.type -eq 'Ready' } | Select-Object -First 1
    $readyOk = $false
    if ($readyCond -and (Get-RagJsonProperty -Object $readyCond -Name 'status') -eq 'True') {
        $readyOk = $true
    }

    if ($phase -ne 'Running' -or -not $readyOk) {
        $reasonVal = Get-RagJsonProperty -Object $pod.status -Name 'reason'
        $reason = if ($null -ne $reasonVal -and '' -ne [string]$reasonVal) { [string]$reasonVal } else { '' }
        $msgVal = Get-RagJsonProperty -Object $readyCond -Name 'message'
        $msg = if ($null -ne $msgVal -and '' -ne [string]$msgVal) { [string]$msgVal } else { '' }
        $detail = @("phase=$phase", "ready=$readyOk", $reason, $msg) -join '; '
        $failures.Add("${name}: $detail")
    }
}

if ($failures.Count -gt 0) {
    Write-Host 'NOT all pods are Running and Ready:' -ForegroundColor Red
    foreach ($line in $failures) {
        Write-Host "  $line" -ForegroundColor Red
    }
    exit 1
}

Write-Host "OK: all $($items.Count) pod(s) are Running and Ready." -ForegroundColor Green
exit 0
