#requires -Version 5.1
<#
.SYNOPSIS
  POST /ingest/package to the vectorizer (parallel to scripts/ingest-package.sh).

.EXAMPLE
  .\Ingest-Package.ps1 BILLS-115hr1625enr
#>
param(
    [Parameter(Position = 0)]
    [string]$PackageId
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$VECTORIZER_URL = if ($env:VECTORIZER_URL) { $env:VECTORIZER_URL.TrimEnd('/') } else { 'http://localhost:8001' }
if (-not $PackageId) {
    $PackageId = $env:PACKAGE_ID
}
$METADATA = if ($env:METADATA) { $env:METADATA } else { '{"source":"ingest-package.ps1"}' }

if (-not $PackageId) {
    Write-Host "usage: $($MyInvocation.MyCommand.Name) <packageId>     (e.g. BILLS-115hr1625enr)"
    Write-Host '       or set PACKAGE_ID env var'
    exit 2
}

Test-RagCommand jq 'Install jq (winget install jqlang.jq).'

$BODY = jq -nc --arg pid $PackageId --argjson md $METADATA '{packageId:$pid, metadata:$md}'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "POST ${VECTORIZER_URL}/ingest/package"
$BODY | jq .
Write-Host ''

$r = Invoke-WebRequest -Uri "${VECTORIZER_URL}/ingest/package" -Method Post -Body $BODY -ContentType 'application/json; charset=utf-8' -UseBasicParsing
$r.Content | jq .
