#requires -Version 5.1
<#
.SYNOPSIS
  Verify a Nova Sonic STS federated session.

.DESCRIPTION
  Checks the current AWS caller identity, reports the remaining credential
  lifetime when SONIC_AWS_CREDENTIAL_EXPIRATION is present, and probes Bedrock
  model access for the Nova Sonic model.

.EXAMPLE
  .\scripts\ps\Check-NovaSonic.ps1

.EXAMPLE
  .\scripts\ps\Check-NovaSonic.ps1 -EnvFile .\env.nova-sonic-sts

.EXAMPLE
  .\scripts\ps\Check-NovaSonic.ps1 -ShowAwsError
#>
param(
    [Parameter(Position = 0)]
    [string]$EnvFile = '',
    [switch]$ShowAwsError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

function Import-NovaEnvFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.TrimEnd("`r")
        $trim = $line.Trim()
        if ($trim -eq '' -or $trim.StartsWith('#')) {
            return
        }

        if ($trim.StartsWith('export ')) {
            $trim = $trim.Substring('export '.Length).TrimStart()
        }

        $eq = $trim.IndexOf('=')
        if ($eq -lt 1) {
            return
        }

        $key = $trim.Substring(0, $eq).Trim()
        $value = $trim.Substring($eq + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "env:$key" -Value $value
    }
}

function Use-NovaSonicAwsCredentials {
    param(
        [Parameter(Mandatory)]
        [string]$SourcePath
    )

    $missing = @()
    if (-not $env:SONIC_AWS_ACCESS_KEY_ID) {
        $missing += 'SONIC_AWS_ACCESS_KEY_ID'
    }
    if (-not $env:SONIC_AWS_SECRET_ACCESS_KEY) {
        $missing += 'SONIC_AWS_SECRET_ACCESS_KEY'
    }

    if ($missing.Count -gt 0) {
        [Console]::Error.WriteLine("Nova Sonic AWS credentials are missing from ${SourcePath}: $($missing -join ', ')")
        exit 2
    }

    $env:AWS_ACCESS_KEY_ID = $env:SONIC_AWS_ACCESS_KEY_ID
    $env:AWS_SECRET_ACCESS_KEY = $env:SONIC_AWS_SECRET_ACCESS_KEY
    if ($env:SONIC_AWS_SESSION_TOKEN) {
        $env:AWS_SESSION_TOKEN = $env:SONIC_AWS_SESSION_TOKEN
    }
    else {
        [Environment]::SetEnvironmentVariable('AWS_SESSION_TOKEN', $null, 'Process')
    }

    [Environment]::SetEnvironmentVariable('AWS_PROFILE', $null, 'Process')
    [Environment]::SetEnvironmentVariable('AWS_DEFAULT_PROFILE', $null, 'Process')
    $env:AWS_EC2_METADATA_DISABLED = 'true'
}

$repoRoot = Get-RagRepoRoot
$envFileName = if ($EnvFile) { $EnvFile } elseif ($env:ENV_FILE) { $env:ENV_FILE } else { '.env' }
$envPath = if ([System.IO.Path]::IsPathRooted($envFileName)) { $envFileName } else { Join-Path $repoRoot $envFileName }

if (-not (Test-Path -LiteralPath $envPath)) {
    [Console]::Error.WriteLine("env file not found: $envPath")
    exit 2
}

Import-NovaEnvFile -Path $envPath
Use-NovaSonicAwsCredentials -SourcePath $envPath

$region = if ($env:AWS_REGION) { $env:AWS_REGION } else { 'us-east-1' }
$modelId = if ($env:BEDROCK_NOVA_SONIC_MODEL_ID) { $env:BEDROCK_NOVA_SONIC_MODEL_ID } else { 'amazon.nova-sonic-v1:0' }

Test-RagCommand aws 'Install AWS CLI v2.'

Write-Host '== STS identity =='
aws sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) {
    Write-Error 'STS call failed - credentials are invalid or expired.'
    exit 1
}

Write-Host
Write-Host '== Session lifetime =='
if ($env:SONIC_AWS_CREDENTIAL_EXPIRATION) {
    $expiration = [System.DateTimeOffset]::MinValue
    $dateStyle = [System.Globalization.DateTimeStyles]::AssumeUniversal
    if ([System.DateTimeOffset]::TryParse(
            $env:SONIC_AWS_CREDENTIAL_EXPIRATION,
            [System.Globalization.CultureInfo]::InvariantCulture,
            $dateStyle,
            [ref]$expiration)) {
        $remaining = $expiration.ToUniversalTime() - [System.DateTimeOffset]::UtcNow
        if ($remaining.TotalSeconds -gt 0) {
            $hours = [math]::Floor($remaining.TotalHours)
            $minutes = [math]::Floor($remaining.Minutes)
            Write-Host "expires:   $env:SONIC_AWS_CREDENTIAL_EXPIRATION"
            Write-Host "remaining: ${hours}h ${minutes}m"
        }
        else {
            Write-Host "expired at $env:SONIC_AWS_CREDENTIAL_EXPIRATION"
        }
    }
    else {
        Write-Host "expires: $env:SONIC_AWS_CREDENTIAL_EXPIRATION (could not parse for delta)"
    }
}
else {
    Write-Host 'SONIC_AWS_CREDENTIAL_EXPIRATION not set in env file'
}

Write-Host
Write-Host "== Bedrock permission probe ($modelId, $region) =="
# Nova Sonic only supports InvokeModelWithBidirectionalStream, so a regular
# invoke-model call will never succeed. The type of error tells us about auth.
$tmpOut = [System.IO.Path]::GetTempFileName()
$tmpErr = [System.IO.Path]::GetTempFileName()

try {
    $awsArgs = @(
        'bedrock-runtime', 'invoke-model',
        '--region', $region,
        '--model-id', $modelId,
        '--content-type', 'application/json',
        '--accept', 'application/json',
        '--cli-binary-format', 'raw-in-base64-out',
        '--body', '{"ping":1}',
        $tmpOut
    )

    $awsCommand = Get-Command aws -CommandType Application -ErrorAction Stop
    $process = Start-Process -FilePath $awsCommand.Source -ArgumentList $awsArgs -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
    $rc = [int]$process.ExitCode
    $errText = Get-Content -LiteralPath $tmpErr -Raw

    if ($rc -eq 0) {
        Write-Host 'unexpected success - Nova Sonic accepted a plain invoke-model call?'
        Get-Content -LiteralPath $tmpOut
        exit 0
    }

    if ($errText -match 'ExpiredTokenException|InvalidClientTokenId|TokenRefreshRequired') {
        Write-Host 'RESULT: credentials are dead (expired/invalid).'
        Write-Host $errText
        exit 1
    }
    elseif ($errText -match 'AccessDeniedException|not authorized') {
        Write-Host 'RESULT: credentials valid, but principal lacks bedrock:InvokeModel on this model.'
        Write-Host '       (This does NOT rule out bedrock:InvokeModelWithBidirectionalStream - the'
        Write-Host '        BedrockNovaSonicOnly role is likely scoped to the bidirectional action only.)'
        if ($ShowAwsError) {
            Write-Host
            Write-Host $errText
        }
        exit 0
    }
    elseif ($errText -match 'ValidationException|bidirectional|only supports') {
        Write-Host 'RESULT: credentials + Bedrock model access OK.'
        Write-Host '       (Model rejected the non-streaming API shape, which is expected.)'
        if ($ShowAwsError) {
            Write-Host
            Write-Host $errText
        }
        exit 0
    }
    else {
        Write-Host 'RESULT: unrecognized error - review below.'
        Write-Host $errText
        exit 1
    }
}
finally {
    Remove-Item -LiteralPath $tmpOut, $tmpErr -Force -ErrorAction SilentlyContinue
}
