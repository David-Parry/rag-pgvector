# Shared helpers for rag-pgvector PowerShell scripts (dot-source from sibling .ps1 files).

# Resolve this file's directory without `$script:` — when _Common.ps1 is dot-sourced into a script
# started via `&` from another script (e.g. Rag.ps1 -> Docker-Desktop-Up.ps1), `$script:*` can bind to
# the wrong script scope under StrictMode and surface as "variable has not been set" on the caller.
$__ragPgVector_PsScriptsRoot = $PSScriptRoot
if (-not $__ragPgVector_PsScriptsRoot) {
    $__ragPgVector_PsScriptsRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Get-RagRepoRoot {
    $scriptsDir = Split-Path -Parent $__ragPgVector_PsScriptsRoot
    return (Resolve-Path (Join-Path $scriptsDir '..')).Path
}

function Import-RagDotEnv {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.TrimEnd("`r")
        $trim = $line.Trim()
        if ($trim -eq '' -or $trim.StartsWith('#')) {
            return
        }
        $eq = $trim.IndexOf('=')
        if ($eq -lt 1) {
            return
        }
        $key = $trim.Substring(0, $eq).Trim()
        $val = $trim.Substring($eq + 1).Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        Set-Item -Path "env:$key" -Value $val
    }
}

function Test-RagCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [string]$InstallHint = ''
    )
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Error "ERROR: '$Name' is not on PATH. $InstallHint"
        exit 1
    }
}

function Invoke-RagKubectlProbe {
    <#
    Run kubectl for existence checks where exit code is authoritative (e.g. resource NotFound).
    Uses redirected stdout/stderr so PowerShell does not treat Kubernetes stderr as a terminating
    error when $ErrorActionPreference is Stop (notably PS 7 native-command integration).
    #>
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )
    $kc = Get-Command kubectl -CommandType Application -ErrorAction Stop
    $exe = $kc.Source
    $outFile = [System.IO.Path]::GetTempFileName()
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $exe -ArgumentList $Arguments -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        return [int]$p.ExitCode
    }
    finally {
        Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-RagStalePortForwardInfo {
    param(
        [Parameter(Mandatory)]
        [string]$Namespace,
        [string]$PostgresSvc = 'rag-postgres'
    )
    $list = [System.Collections.Generic.List[object]]::new()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'kubectl.exe'" -ErrorAction SilentlyContinue) {
        $cmd = $p.CommandLine
        if (-not $cmd) {
            continue
        }
        if ($cmd -notmatch '(?:-n|--namespace)(?:=|\s+)') {
            continue
        }
        if ($cmd -notmatch [regex]::Escape($Namespace)) {
            continue
        }
        if ($cmd -notmatch 'port-forward') {
            continue
        }
        $hitsSvc =
            $cmd -match 'svc/vectorizer' -or
            $cmd -match 'svc/question-api' -or
            $cmd -match ([regex]::Escape("svc/$PostgresSvc"))
        if (-not $hitsSvc) {
            continue
        }
        $list.Add([pscustomobject]@{ ProcessId = [uint32]$p.ProcessId; CommandLine = $cmd })
    }
    return $list
}

function Get-RagAnyNamespacePortForwardInfo {
    param([Parameter(Mandatory)][string]$Namespace)
    $list = [System.Collections.Generic.List[object]]::new()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'kubectl.exe'" -ErrorAction SilentlyContinue) {
        $cmd = $p.CommandLine
        if (-not $cmd) {
            continue
        }
        if ($cmd -notmatch '(?:-n|--namespace)(?:=|\s+)') {
            continue
        }
        if ($cmd -notmatch [regex]::Escape($Namespace)) {
            continue
        }
        if ($cmd -notmatch 'port-forward') {
            continue
        }
        $list.Add([pscustomobject]@{ ProcessId = [uint32]$p.ProcessId; CommandLine = $cmd })
    }
    return $list
}

function Stop-RagProcessesGracefully {
    param([uint32[]]$ProcessIds)
    foreach ($id in $ProcessIds) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
}

function Get-RagPortListenerSummary {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $conn) {
            return $null
        }
        $owningPid = $conn.OwningProcess
        $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { 'process' }
        return "${name} (PID $owningPid)"
    }
    catch {
        return $null
    }
}
