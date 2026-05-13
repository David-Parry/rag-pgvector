#requires -Version 5.1
<#
.SYNOPSIS
  Smoke-test AWS_BEARER_TOKEN_BEDROCK from .env (parallel to scripts/bedrock-smoke.sh).

.NOTES
  Env: ENV_FILE, FULL_VECTOR=1
#>
param(
    [Parameter(Position = 0)]
    [string]$InputTextArg
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$ENV_FILE = if ($env:ENV_FILE) { $env:ENV_FILE } else { '.env' }
$INPUT_TEXT = if ($InputTextArg) { $InputTextArg } else { 'hello bedrock test' }

$ROOT_DIR = Get-RagRepoRoot
$envPath = if ([System.IO.Path]::IsPathRooted($ENV_FILE)) { $ENV_FILE } else { Join-Path $ROOT_DIR $ENV_FILE }

if (-not (Test-Path -LiteralPath $envPath)) {
    Write-Error "missing ${envPath}"
    exit 1
}

Import-RagDotEnv -Path $envPath

$saved = @{}
foreach ($k in @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE')) {
    $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
    [Environment]::SetEnvironmentVariable($k, $null, 'Process')
}

try {
    $tok = $env:AWS_BEARER_TOKEN_BEDROCK
    if (-not $tok -or $tok -eq 'replace-with-bedrock-api-key') {
        Write-Error "AWS_BEARER_TOKEN_BEDROCK is not set in ${envPath}"
        exit 1
    }

    $REGION = if ($env:AWS_REGION) { $env:AWS_REGION } else { 'us-east-1' }
    $MODEL_ID = if ($env:BEDROCK_EMBEDDING_MODEL_ID) { $env:BEDROCK_EMBEDDING_MODEL_ID } else { 'amazon.titan-embed-text-v2:0' }

    Write-Host "[bedrock-smoke] region=${REGION} model=${MODEL_ID} input=${INPUT_TEXT}"

    Test-RagCommand jq 'Install jq (winget install jqlang.jq).'
    Test-RagCommand aws 'Install AWS CLI v2.'

    $BODY = jq -nc --arg t $INPUT_TEXT '{inputText:$t}'
    $OUT = [System.IO.Path]::GetTempFileName()
    try {
        aws bedrock-runtime invoke-model `
            --region $REGION `
            --model-id $MODEL_ID `
            --content-type application/json `
            --accept application/json `
            --cli-binary-format raw-in-base64-out `
            --body $BODY `
            $OUT *> $null
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        if ($env:FULL_VECTOR -eq '1') {
            jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, embedding:.embedding}' $OUT
        }
        else {
            jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, first5:.embedding[0:5]}' $OUT
        }
    }
    finally {
        Remove-Item -LiteralPath $OUT -Force -ErrorAction SilentlyContinue
    }
}
finally {
    foreach ($k in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process')
    }
}
