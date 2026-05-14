#requires -Version 5.1
<#
.SYNOPSIS
  Forward vectorizer, question-api, Postgres, and Redis Stack services to localhost (parallel to scripts/port-forward.sh).

.NOTES
  Env: NAMESPACE, VECTORIZER_PORT, QA_PORT, POSTGRES_PORT, POSTGRES_SVC, REDIS_PORT, REDIS_SVC, KILL_STALE=1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE } else { 'rag' }
$VECTORIZER_PORT = if ($env:VECTORIZER_PORT) { [int]$env:VECTORIZER_PORT } else { 8001 }
$QA_PORT = if ($env:QA_PORT) { [int]$env:QA_PORT } else { 8002 }
$POSTGRES_PORT = if ($env:POSTGRES_PORT) { [int]$env:POSTGRES_PORT } else { 5432 }
$POSTGRES_SVC = if ($env:POSTGRES_SVC) { $env:POSTGRES_SVC } else { 'rag-postgres' }
$REDIS_PORT = if ($env:REDIS_PORT) { [int]$env:REDIS_PORT } else { 6379 }
$REDIS_SVC = if ($env:REDIS_SVC) { $env:REDIS_SVC } else { 'rag-redis-stack' }
$KILL_STALE = if ($env:KILL_STALE) { $env:KILL_STALE } else { '0' }

Test-RagCommand kubectl 'Install kubectl.'

if (-not (Test-RagKubernetesNamespaceExists -Namespace $NAMESPACE)) {
    Write-Error "Namespace '$NAMESPACE' does not exist. Run Helm install first or set NAMESPACE to an existing namespace."
    exit 1
}

$stale = @(Get-RagStalePortForwardInfo -Namespace $NAMESPACE -PostgresSvc $POSTGRES_SVC -RedisSvc $REDIS_SVC)
if ($stale.Count -gt 0) {
    Write-Host 'Detected stale kubectl port-forwards from a previous run:'
    foreach ($s in $stale) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $($s.ProcessId)"
        $cmd = if ($cim) { $cim.CommandLine } else { '' }
        Write-Host "  PID $($s.ProcessId)  $cmd"
    }
    if ($KILL_STALE -eq '1') {
        Write-Host 'KILL_STALE=1 set — reaping...'
        Stop-RagProcessesGracefully -ProcessIds ($stale | ForEach-Object { [uint32]$_.ProcessId })
        Start-Sleep -Seconds 1
        $left = @(Get-RagStalePortForwardInfo -Namespace $NAMESPACE -PostgresSvc $POSTGRES_SVC -RedisSvc $REDIS_SVC)
        if ($left.Count -gt 0) {
            Stop-RagProcessesGracefully -ProcessIds ($left | ForEach-Object { [uint32]$_.ProcessId })
        }
    }
    else {
        $ids = ($stale | ForEach-Object { $_.ProcessId }) -join ' '
        Write-Host ''
        Write-Error "Re-run with `$env:KILL_STALE='1' or kill PIDs: $ids"
        exit 1
    }
}

$blocked = $false
$checks = @(
    @{ Label = 'vectorizer'; Port = $VECTORIZER_PORT },
    @{ Label = 'question-api'; Port = $QA_PORT },
    @{ Label = $POSTGRES_SVC; Port = $POSTGRES_PORT },
    @{ Label = $REDIS_SVC; Port = $REDIS_PORT }
)
foreach ($c in $checks) {
    $holder = Get-RagPortListenerSummary -Port $c.Port
    if ($holder) {
        Write-Host "ERROR: port $($c.Port) (for $($c.Label)) is held by $holder"
        $blocked = $true
    }
}
if ($blocked) {
    Write-Host ''
    Write-Error 'Free the ports above (or override e.g. VECTORIZER_PORT=8011) and re-run.'
    exit 1
}

Write-Host "Forwarding (namespace=${NAMESPACE}):"
Write-Host "  http://localhost:${VECTORIZER_PORT}     -> svc/vectorizer:8000"
Write-Host "  http://localhost:${QA_PORT}             -> svc/question-api:8000"
Write-Host "  postgresql://localhost:${POSTGRES_PORT} -> svc/${POSTGRES_SVC}:5432"
Write-Host "  redis://localhost:${REDIS_PORT}         -> svc/${REDIS_SVC}:6379"
Write-Host ''

$procs = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

try {
    $procs.Add((Start-Process -FilePath kubectl -ArgumentList @(
            '-n', $NAMESPACE, 'port-forward', 'svc/vectorizer', "${VECTORIZER_PORT}:8000"
        ) -PassThru -WindowStyle Hidden))

    $procs.Add((Start-Process -FilePath kubectl -ArgumentList @(
            '-n', $NAMESPACE, 'port-forward', 'svc/question-api', "${QA_PORT}:8000"
        ) -PassThru -WindowStyle Hidden))

    $procs.Add((Start-Process -FilePath kubectl -ArgumentList @(
            '-n', $NAMESPACE, 'port-forward', "svc/${POSTGRES_SVC}", "${POSTGRES_PORT}:5432"
        ) -PassThru -WindowStyle Hidden))

    $procs.Add((Start-Process -FilePath kubectl -ArgumentList @(
            '-n', $NAMESPACE, 'port-forward', "svc/${REDIS_SVC}", "${REDIS_PORT}:6379"
        ) -PassThru -WindowStyle Hidden))

    Wait-Process -InputObject ($procs | ForEach-Object { $_ })
}
finally {
    Write-Host ''
    Write-Host 'Stopping port-forwards...'
    foreach ($p in $procs) {
        if ($null -ne $p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
