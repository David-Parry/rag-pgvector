#requires -Version 5.1
<#
.SYNOPSIS
  Run the DeepEval pgvector retriever benchmark and write a markdown report.

.NOTES
  This script expects the vector database environment to be running already.
  It does not start, stop, tear down, delete, or reset the database.

  Env: PACKAGE_ID, TOP_K_GRID, THRESHOLD_GRID, DEEPEVAL_TOP_K_GRID,
       DEEPEVAL_THRESHOLD_GRID, DEEPEVAL_REPORT_DIR, DEEPEVAL_REPORT_PATH,
       DEEPEVAL_REPORT_FILE_TYPE, DEEPEVAL_LOG_PATH,
       DATABASE_URL, ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_FILE,
       DEEPEVAL_LOG_LEVEL
#>
param(
    [string]$PackageId,
    [string]$TopKGrid,
    [string]$ThresholdGrid,
    [string]$ReportPath,
    [string]$ReportDir,
    [ValidateSet('markdown', 'html')]
    [string]$ReportFileType
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

function Import-RagAnthropicApiKey {
    param([Parameter(Mandatory)][string]$RepoRoot)

    if (-not [string]::IsNullOrWhiteSpace($env:ANTHROPIC_API_KEY)) {
        return
    }

    $keyFile = if ($env:ANTHROPIC_API_KEY_FILE) {
        $env:ANTHROPIC_API_KEY_FILE
    }
    else {
        Join-Path $RepoRoot 'claudeapi.txt'
    }
    if (-not [System.IO.Path]::IsPathRooted($keyFile)) {
        $keyFile = Join-Path $RepoRoot $keyFile
    }
    if (Test-Path -LiteralPath $keyFile) {
        $env:ANTHROPIC_API_KEY = (Get-Content -LiteralPath $keyFile -Raw).Trim()
    }
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
Import-RagAnthropicApiKey -RepoRoot $repoRoot
$env:LOG_LEVEL = Get-RagEnvValue -Name 'DEEPEVAL_LOG_LEVEL' -Default 'INFO'
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
$effectiveReportFileType = if ($ReportFileType) {
    $ReportFileType
}
else {
    Get-RagEnvValue -Name 'DEEPEVAL_REPORT_FILE_TYPE' -Default 'markdown'
}
$effectiveReportFileType = $effectiveReportFileType.ToLowerInvariant()
if ($effectiveReportFileType -eq 'md') {
    $effectiveReportFileType = 'markdown'
}
if ($effectiveReportFileType -notin @('markdown', 'html')) {
    Write-Error "DEEPEVAL_REPORT_FILE_TYPE must be 'markdown' or 'html'."
    exit 1
}
$env:DEEPEVAL_REPORT_FILE_TYPE = $effectiveReportFileType
$reportExtension = if ($effectiveReportFileType -eq 'html') { '.html' } else { '.md' }
$safePackageId = Get-RagSafeFilePart -Value $effectivePackageId
$effectiveReportPath = if ($ReportPath) {
    $ReportPath
}
else {
    Get-RagEnvValue -Name 'DEEPEVAL_REPORT_PATH' -Default (Join-Path $effectiveReportDir "deepeval-${safePackageId}-${timestamp}${reportExtension}")
}

$reportFullPath = if ([System.IO.Path]::IsPathRooted($effectiveReportPath)) {
    $effectiveReportPath
}
else {
    Join-Path $repoRoot $effectiveReportPath
}
$effectiveLogPath = Get-RagEnvValue -Name 'DEEPEVAL_LOG_PATH' -Default ([System.IO.Path]::ChangeExtension($effectiveReportPath, '.log'))
$logFullPath = if ([System.IO.Path]::IsPathRooted($effectiveLogPath)) {
    $effectiveLogPath
}
else {
    Join-Path $repoRoot $effectiveLogPath
}
$reportParent = Split-Path -Parent $reportFullPath
if ($reportParent) {
    New-Item -ItemType Directory -Force -Path $reportParent | Out-Null
}
$logParent = Split-Path -Parent $logFullPath
if ($logParent) {
    New-Item -ItemType Directory -Force -Path $logParent | Out-Null
}

$header = if ($effectiveReportFileType -eq 'html') {
    $htmlPackageId = [System.Net.WebUtility]::HtmlEncode($effectivePackageId)
    $htmlTopKGrid = [System.Net.WebUtility]::HtmlEncode($effectiveTopKGrid)
    $htmlThresholdGrid = [System.Net.WebUtility]::HtmlEncode($effectiveThresholdGrid)
    $htmlLogPath = [System.Net.WebUtility]::HtmlEncode($effectiveLogPath)
    @(
        '<!doctype html>'
        '<html lang="en">'
        '<head>'
        '  <meta charset="utf-8">'
        '  <title>DeepEval Retriever Benchmark Report</title>'
        '  <style>body{font-family:Arial,sans-serif;line-height:1.5;margin:2rem;max-width:1100px}table{border-collapse:collapse;width:100%;margin-top:1rem}th,td{border:1px solid #d0d7de;padding:.45rem;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#f6f8fa}code{background:#f6f8fa;padding:.15rem .3rem;border-radius:4px}</style>'
        '</head>'
        '<body>'
        '<main>'
        '<h1>DeepEval Retriever Benchmark Report</h1>'
        '<ul>'
        "  <li>Generated: $generatedAt</li>"
        "  <li>Package ID: <code>$htmlPackageId</code></li>"
        "  <li>Top-k grid: <code>$htmlTopKGrid</code></li>"
        "  <li>Threshold grid: <code>$htmlThresholdGrid</code></li>"
        "  <li>Progress log: <code>$htmlLogPath</code></li>"
        '</ul>'
    )
}
else {
    @(
        '# DeepEval Retriever Benchmark Report'
        ''
        "- Generated: $generatedAt"
        "- Package ID: $effectivePackageId"
        "- Top-k grid: $effectiveTopKGrid"
        "- Threshold grid: $effectiveThresholdGrid"
        "- Progress log: $effectiveLogPath"
        ''
    )
}

$header | Tee-Object -FilePath $reportFullPath | Out-Host
Write-Host "DeepEval progress log is being written to $effectiveLogPath"
$oldErrorActionPreference = $ErrorActionPreference
$oldNativeCommandPreference = $null
$hasNativeCommandPreference = Test-Path -LiteralPath 'Variable:\PSNativeCommandUseErrorActionPreference'
if ($hasNativeCommandPreference) {
    $oldNativeCommandPreference = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
}
try {
    $ErrorActionPreference = 'Continue'
    & uv run python -m rag_evals.cli 2> $logFullPath | Tee-Object -FilePath $reportFullPath -Append
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        if ($effectiveReportFileType -eq 'html') {
            "<section><h2>Error</h2><p>The eval command failed. See the progress log for command output: <code>$([System.Net.WebUtility]::HtmlEncode($effectiveLogPath))</code></p></section>" | Tee-Object -FilePath $reportFullPath -Append | Out-Host
        }
        else {
            @(
                ''
                '## Error'
                ''
                "The eval command failed. See the progress log for command output: $effectiveLogPath"
            ) | Tee-Object -FilePath $reportFullPath -Append | Out-Host
        }
    }
}
finally {
    $ErrorActionPreference = $oldErrorActionPreference
    if ($hasNativeCommandPreference) {
        $PSNativeCommandUseErrorActionPreference = $oldNativeCommandPreference
    }
}

if ($effectiveReportFileType -eq 'html') {
    @(
        '</main>'
        '</body>'
        '</html>'
    ) | Tee-Object -FilePath $reportFullPath -Append | Out-Null
}

Write-Host "DeepEval report written to $effectiveReportPath"
Write-Host "DeepEval progress log written to $effectiveLogPath"
exit $exitCode
