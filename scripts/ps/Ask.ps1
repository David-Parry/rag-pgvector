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

$QUESTION_API_URL = if ($env:QUESTION_API_URL) { $env:QUESTION_API_URL.TrimEnd('/') } else { 'http://localhost:8002' }

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

Test-RagCommand jq 'Install jq (winget install jqlang.jq).'

$BODY = jq -nc `
    --arg q $QUESTION `
    --argjson md $METADATA `
    --arg topk $TOP_K `
    --arg score $SCORE_THRESHOLD `
    '{question:$q, metadata:$md}
    + (if $topk  == "" then {} else {topK:        ($topk  | tonumber)} end)
    + (if $score == "" then {} else {scoreThreshold:($score | tonumber)} end)'
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "POST ${QUESTION_API_URL}/ask"
$BODY | jq .
Write-Host ''

$r = Invoke-WebRequest -Uri "${QUESTION_API_URL}/ask" -Method Post -Body $BODY -ContentType 'application/json; charset=utf-8' -UseBasicParsing
$RESPONSE = $r.Content

if ($env:RAW -eq '1') {
    $RESPONSE | jq .
    exit 0
}

$RESPONSE | jq -r '
  "=== answer (provider=" + .provider + ", usedContextCount=" + (.usedContextCount|tostring) + ") ===",
  "",
  .answer,
  "",
  "=== citations ===",
  (.citations
   | to_entries[]
   | "[" + ((.key + 1)|tostring) + "] "
       + (.value.packageId // "?")
       + (if .value.pageNumber != null then " p." + (.value.pageNumber|tostring) else "" end)
       + "  score=" + ((.value.score|tostring) | .[0:6])
       + "\n     " + (.value.sourceUrl // "")
       + "\n     " + (.value.snippet // "" | gsub("\\s+"; " ") | .[0:220])
  )'
