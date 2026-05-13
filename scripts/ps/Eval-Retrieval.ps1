#requires -Version 5.1
<#
.SYNOPSIS
  Run the DeepEval pgvector retriever benchmark and write a markdown report.

.NOTES
  This script expects the vector database environment to be running already.
  It does not start, stop, tear down, delete, or reset the database.

  Env: PACKAGE_ID, TOP_K_GRID, THRESHOLD_GRID, DEEPEVAL_TOP_K_GRID,
       DEEPEVAL_THRESHOLD_GRID, DEEPEVAL_REPORT_DIR, DEEPEVAL_REPORT_PATH,
       DATABASE_URL
#>
param(
    [string]$PackageId,
    [string]$TopKGrid,
    [string]$ThresholdGrid,
    [string]$ReportPath,
    [string]$ReportDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

function Get-RagEnvValue {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [string]$Default = ''
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function Get-RagSafeFilePart {
    param([Parameter(Mandatory)][string]$Value)
    return ($Value -replace '[^A-Za-z0-9._-]', '_')
}

function Test-RagDatabaseReachable {
    param([Parameter(Mandatory)][string]$DatabaseUrl)

    $uriText = $DatabaseUrl -replace '^postgresql\+psycopg:', 'postgresql:'
    try {
        $uri = [System.Uri]$uriText
    }
    catch {
        Write-Error "DATABASE_URL is not a valid PostgreSQL URL: $DatabaseUrl"
        exit 1
    }

    $hostName = $uri.Host
    $port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
    Write-Host "Checking existing pgvector database at ${hostName}:${port} ..."
    $reachable = Test-NetConnection -ComputerName $hostName -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
    if (-not $reachable) {
        Write-Error "pgvector database is not reachable at ${hostName}:${port}. Start the environment and port-forward Postgres first, for example: .\scripts\ps\Rag.ps1 port-forward"
        exit 1
    }
}

$repoRoot = Get-RagRepoRoot
Set-Location -LiteralPath $repoRoot
Import-RagDotEnv -Path (Join-Path $repoRoot '.env')
Test-RagCommand -Name 'uv' -InstallHint 'Install uv from https://docs.astral.sh/uv/.'

$databaseUrl = Get-RagEnvValue -Name 'DATABASE_URL'
if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
    Write-Error 'DATABASE_URL is required. Start the environment and set DATABASE_URL before running eval retrieval.'
    exit 1
}
Test-RagDatabaseReachable -DatabaseUrl $databaseUrl

$effectivePackageId = if ($PackageId) { $PackageId } else { Get-RagEnvValue -Name 'PACKAGE_ID' -Default 'BILLS-115hr1625enr' }
$effectiveTopKGrid = if ($TopKGrid) {
    $TopKGrid
}
else {
    Get-RagEnvValue -Name 'TOP_K_GRID' -Default (Get-RagEnvValue -Name 'DEEPEVAL_TOP_K_GRID' -Default '3,5,8')
}
$effectiveThresholdGrid = if ($ThresholdGrid) {
    $ThresholdGrid
}
else {
    Get-RagEnvValue -Name 'THRESHOLD_GRID' -Default (Get-RagEnvValue -Name 'DEEPEVAL_THRESHOLD_GRID' -Default '0.4,0.6,0.8')
}

$env:PACKAGE_ID = $effectivePackageId
$env:DEEPEVAL_TOP_K_GRID = $effectiveTopKGrid
$env:DEEPEVAL_THRESHOLD_GRID = $effectiveThresholdGrid

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$generatedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$effectiveReportDir = if ($ReportDir) { $ReportDir } else { Get-RagEnvValue -Name 'DEEPEVAL_REPORT_DIR' -Default 'documentation/eval-reports' }
$safePackageId = Get-RagSafeFilePart -Value $effectivePackageId
$effectiveReportPath = if ($ReportPath) {
    $ReportPath
}
else {
    Get-RagEnvValue -Name 'DEEPEVAL_REPORT_PATH' -Default (Join-Path $effectiveReportDir "deepeval-${safePackageId}-${timestamp}.md")
}

$reportFullPath = if ([System.IO.Path]::IsPathRooted($effectiveReportPath)) {
    $effectiveReportPath
}
else {
    Join-Path $repoRoot $effectiveReportPath
}
$reportParent = Split-Path -Parent $reportFullPath
if ($reportParent) {
    New-Item -ItemType Directory -Force -Path $reportParent | Out-Null
}

$header = @(
    '# DeepEval Retriever Benchmark Report'
    ''
    "- Generated: $generatedAt"
    "- Package ID: $effectivePackageId"
    "- Top-k grid: $effectiveTopKGrid"
    "- Threshold grid: $effectiveThresholdGrid"
    ''
)

$header | Tee-Object -FilePath $reportFullPath | Out-Host
& uv run python -m rag_evals.cli 2>&1 | Tee-Object -FilePath $reportFullPath -Append
$exitCode = $LASTEXITCODE

Write-Host "DeepEval report written to $effectiveReportPath"
exit $exitCode
