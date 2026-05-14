#requires -Version 5.1
<#
.SYNOPSIS
  POST /ask to question-api (parallel to scripts/ask.sh).

.NOTES
  Env: QUESTION_API_URL, QUESTION, METADATA, TOP_K, SCORE_THRESHOLD, RAW=1
#>
param(
    [Parameter(Position = 0)]
    [string]$QuestionArg
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$QUESTION_API_URL = if ($env:QUESTION_API_URL) { $env:QUESTION_API_URL.TrimEnd('/') } else { 'http://localhost:8000' }

$DEFAULT_QUESTION = 'What conditions does the Consolidated Appropriations Act place on U.S. assistance to the West Bank and Gaza, and what restrictions apply to the Palestinian Authority?'
if ($QuestionArg) {
    $QUESTION = $QuestionArg
}
elseif ($env:QUESTION) {
    $QUESTION = $env:QUESTION
}
else {
    $QUESTION = $DEFAULT_QUESTION
}

$METADATA = if ($env:METADATA) { $env:METADATA } else { '{}' }
$TOP_K = if ($env:TOP_K) { $env:TOP_K } else { '6' }
$SCORE_THRESHOLD = if ($env:SCORE_THRESHOLD) { $env:SCORE_THRESHOLD } else { '0.80' }

$bodyObject = [ordered]@{
    question = $QUESTION
    metadata = ($METADATA | ConvertFrom-Json)
}
if ($TOP_K -ne '') {
    $bodyObject['topK'] = [int]$TOP_K
}
if ($SCORE_THRESHOLD -ne '') {
    $bodyObject['scoreThreshold'] = [double]$SCORE_THRESHOLD
}
$BODY = $bodyObject | ConvertTo-Json -Depth 20 -Compress

Write-Host "POST ${QUESTION_API_URL}/ask"
($BODY | ConvertFrom-Json) | ConvertTo-Json -Depth 20
Write-Host ''

$r = Invoke-WebRequest -Uri "${QUESTION_API_URL}/ask" -Method Post -Body $BODY -ContentType 'application/json; charset=utf-8' -UseBasicParsing
$RESPONSE = $r.Content

if ($env:RAW -eq '1') {
    ($RESPONSE | ConvertFrom-Json) | ConvertTo-Json -Depth 20
    exit 0
}

$parsed = $RESPONSE | ConvertFrom-Json
Write-Host "=== answer (provider=$($parsed.provider), usedContextCount=$($parsed.usedContextCount)) ==="
Write-Host ''
Write-Host $parsed.answer
Write-Host ''
Write-Host '=== citations ==='
for ($i = 0; $i -lt $parsed.citations.Count; $i++) {
    $citation = $parsed.citations[$i]
    $page = if ($null -ne $citation.pageNumber) { " p.$($citation.pageNumber)" } else { '' }
    $snippet = if ($citation.snippet) {
        ($citation.snippet -replace '\s+', ' ').Substring(0, [Math]::Min(220, ($citation.snippet -replace '\s+', ' ').Length))
    }
    else {
        ''
    }
    Write-Host "[$($i + 1)] $($citation.packageId)$page  score=$('{0:N4}' -f [double]$citation.score)"
    Write-Host "     $($citation.sourceUrl)"
    Write-Host "     $snippet"
}
