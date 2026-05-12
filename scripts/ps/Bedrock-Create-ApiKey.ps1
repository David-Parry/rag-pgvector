#requires -Version 5.1
<#
.SYNOPSIS
  Create Bedrock bearer API key and append to .env (parallel to scripts/bedrock-create-api-key.sh).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$AWS_PROFILE = if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { 'default' }
$AWS_REGION = if ($env:AWS_REGION) { $env:AWS_REGION } else { 'us-east-1' }
$IAM_USER = if ($env:IAM_USER) { $env:IAM_USER } else { 'bedrock-rag-pgvector-dev' }
$POLICY_NAME = if ($env:POLICY_NAME) { $env:POLICY_NAME } else { 'BedrockInvokeTitanEmbedV2' }
$MODEL_ID = if ($env:MODEL_ID) { $env:MODEL_ID } else { 'amazon.titan-embed-text-v2:0' }
$CREDENTIAL_AGE_DAYS = if ($env:CREDENTIAL_AGE_DAYS) { $env:CREDENTIAL_AGE_DAYS } else { '15' }
$ENV_FILE = if ($env:ENV_FILE) { $env:ENV_FILE } else { '.env' }

$env:AWS_PROFILE = $AWS_PROFILE
$env:AWS_REGION = $AWS_REGION

function Write-BedrockLog([string]$Message) {
    Write-Host ''
    Write-Host "[bedrock-key] $Message"
}

Test-RagCommand aws 'Install AWS CLI v2.'
Test-RagCommand jq 'Install jq (winget install jqlang.jq).'

$ROOT_DIR = Get-RagRepoRoot
$envPath = if ([System.IO.Path]::IsPathRooted($ENV_FILE)) { $ENV_FILE } else { Join-Path $ROOT_DIR $ENV_FILE }

$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text).Trim()
$MODEL_ARN = "arn:aws:bedrock:${AWS_REGION}::foundation-model/${MODEL_ID}"
Write-BedrockLog "account=${ACCOUNT_ID} region=${AWS_REGION} user=${IAM_USER}"
Write-BedrockLog "model_arn=${MODEL_ARN}"

Write-BedrockLog "Checking ${MODEL_ID} is listed in ${AWS_REGION}..."
$listed = aws bedrock list-foundation-models --region $AWS_REGION --query "modelSummaries[?modelId=='${MODEL_ID}'].modelId" --output text
if (-not ($listed -match [regex]::Escape($MODEL_ID))) {
    Write-Error "model ${MODEL_ID} not listed in ${AWS_REGION}"
    exit 1
}

aws iam get-user --user-name $IAM_USER 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-BedrockLog "IAM user ${IAM_USER} already exists, reusing"
}
else {
    Write-BedrockLog "Creating IAM user ${IAM_USER}"
    aws iam create-user --user-name $IAM_USER *> $null
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-BedrockLog "Putting inline policy ${POLICY_NAME}"
$POLICY_DOC = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBearerTokenAuth",
      "Effect": "Allow",
      "Action": ["bedrock:CallWithBearerToken"],
      "Resource": "*"
    },
    {
      "Sid": "AllowInvokeTitanEmbedV2",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": ["${MODEL_ARN}"]
    }
  ]
}
"@
aws iam put-user-policy --user-name $IAM_USER --policy-name $POLICY_NAME --policy-document $POLICY_DOC
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-BedrockLog "Creating Bedrock API key (expires in ${CREDENTIAL_AGE_DAYS} days)"
$prevEa = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $KEY_JSON = aws iam create-service-specific-credential --user-name $IAM_USER --service-name bedrock.amazonaws.com --credential-age-days $CREDENTIAL_AGE_DAYS 2>&1 | Out-String
}
finally {
    $ErrorActionPreference = $prevEa
}

if ($LASTEXITCODE -ne 0) {
    if ($KEY_JSON -match '(?i)credential-age-days|Unknown options') {
        Write-BedrockLog 'CLI rejected --credential-age-days; retrying with default lifetime'
        $KEY_JSON = aws iam create-service-specific-credential --user-name $IAM_USER --service-name bedrock.amazonaws.com 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Error $KEY_JSON
            exit 1
        }
    }
    else {
        Write-Error $KEY_JSON
        exit 1
    }
}

$BEARER_TOKEN = ($KEY_JSON | jq -r '.ServiceSpecificCredential.ServiceCredentialSecret // .ServiceSpecificCredential.ServicePassword // empty').Trim()
$KEY_ID = ($KEY_JSON | jq -r '.ServiceSpecificCredential.ServiceSpecificCredentialId // .ServiceSpecificCredential.ServiceCredentialAlias // empty').Trim()
$EXPIRES_ON = ($KEY_JSON | jq -r '.ServiceSpecificCredential.ExpirationDate // empty').Trim()

if (-not $BEARER_TOKEN) {
    Write-Error "could not extract bearer token; raw response follows:`n$KEY_JSON"
    exit 1
}
Write-BedrockLog "key_id=${KEY_ID} expires=${EXPIRES_ON}"

Write-BedrockLog "Writing AWS_BEARER_TOKEN_BEDROCK into ${envPath}"
if (-not (Test-Path -LiteralPath $envPath)) {
    New-Item -Path $envPath -ItemType File -Force | Out-Null
}
$lines = @(Get-Content -LiteralPath $envPath)
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^AWS_BEARER_TOKEN_BEDROCK=') {
        $lines[$i] = "AWS_BEARER_TOKEN_BEDROCK=${BEARER_TOKEN}"
        $found = $true
        break
    }
}
if (-not $found) {
    $lines += "AWS_BEARER_TOKEN_BEDROCK=${BEARER_TOKEN}"
}
Set-Content -LiteralPath $envPath -Value $lines -Encoding utf8

Write-BedrockLog "Smoke-testing the new key against ${MODEL_ID}"
$TMP_OUT = [System.IO.Path]::GetTempFileName()
try {
    $saved = @{}
    foreach ($k in @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE')) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, $null, 'Process')
    }
    try {
        $env:AWS_BEARER_TOKEN_BEDROCK = $BEARER_TOKEN
        aws bedrock-runtime invoke-model `
            --region $AWS_REGION `
            --model-id $MODEL_ID `
            --content-type application/json `
            --accept application/json `
            --cli-binary-format raw-in-base64-out `
            --body '{"inputText":"hello bedrock test"}' `
            $TMP_OUT *> $null
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        foreach ($k in $saved.Keys) {
            [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process')
        }
    }

    jq '{dim:(.embedding|length), tokens:.inputTextTokenCount, first5:.embedding[0:5]}' $TMP_OUT
}
finally {
    Remove-Item -LiteralPath $TMP_OUT -Force -ErrorAction SilentlyContinue
}

Write-BedrockLog "done. ${envPath} now has AWS_BEARER_TOKEN_BEDROCK set."
