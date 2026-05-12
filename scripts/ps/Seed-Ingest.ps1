#requires -Version 5.1
<#
.SYNOPSIS
  Sample POST /ingest (parallel to scripts/seed-ingest.sh).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$VECTORIZER_URL = if ($env:VECTORIZER_URL) { $env:VECTORIZER_URL.TrimEnd('/') } else { 'http://localhost:8001' }
$COLLECTION = if ($env:COLLECTION) { $env:COLLECTION } else { 'BILLS' }
$START = if ($env:LAST_MODIFIED_START) { $env:LAST_MODIFIED_START } else { '2026-01-01T00:00:00Z' }
$END = if ($env:LAST_MODIFIED_END) { $env:LAST_MODIFIED_END } else { '' }
$PAGE_SIZE = [int](if ($env:PAGE_SIZE) { $env:PAGE_SIZE } else { '25' })
$MAX_PACKAGES = [int](if ($env:MAX_PACKAGES) { $env:MAX_PACKAGES } else { '5' })

$payload = [ordered]@{
    collection               = $COLLECTION
    lastModifiedStartDate    = $START
    pageSize                 = $PAGE_SIZE
    maxPackages              = $MAX_PACKAGES
    metadata                 = @{ tag = 'demo' }
}
if ($END) {
    $payload['lastModifiedEndDate'] = $END
}

$BODY = $payload | ConvertTo-Json -Compress -Depth 5

Write-Host "POST ${VECTORIZER_URL}/ingest"
Write-Host $BODY
Write-Host ''

$r = Invoke-WebRequest -Uri "${VECTORIZER_URL}/ingest" -Method Post -Body $BODY -ContentType 'application/json; charset=utf-8' -UseBasicParsing
Write-Host $r.Content
Write-Host ''
