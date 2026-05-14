#requires -Version 5.1
<#
.SYNOPSIS
  Install or upgrade the rag-pgvector Helm chart (parallel to scripts/helm-install.sh).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

function Get-RagDotEnvKeys {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }
    $keys = [System.Collections.Generic.List[string]]::new()
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
        if ($key) {
            $null = $keys.Add($key)
        }
    }
    return @($keys | Select-Object -Unique)
}

function Get-RagEnv {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$Default = ''
    )
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -ne $value -and $value -ne '') {
        return $value
    }
    return $Default
}

$ROOT_DIR = Get-RagRepoRoot
Set-Location $ROOT_DIR

$envPath = Join-Path $ROOT_DIR '.env'
$sessionEnvBeforeDotEnv = @{}
Get-ChildItem Env: | ForEach-Object {
    $sessionEnvBeforeDotEnv[$_.Name] = $_.Value
}
$dotEnvKeys = Get-RagDotEnvKeys -Path $envPath
Import-RagDotEnv -Path $envPath

# Values already set in the current shell, including values produced by helper
# scripts such as env_var_artifactory.ps1, should win over .env defaults.
foreach ($key in $dotEnvKeys) {
    if ($sessionEnvBeforeDotEnv.ContainsKey($key) -and $sessionEnvBeforeDotEnv[$key] -ne '') {
        Set-Item -Path "env:$key" -Value $sessionEnvBeforeDotEnv[$key]
    }
}

$RELEASE = if ($env:RELEASE) { $env:RELEASE } else { 'rag' }
$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE } else { 'rag' }
$TAG = if ($env:TAG) { $env:TAG } else { '0.1.0' }
$VALUES_FILE = if ($env:VALUES_FILE) { $env:VALUES_FILE } else { '' }

if (-not $env:ANTHROPIC_API_KEY) {
    $anthropicKeyFile = if ($env:ANTHROPIC_API_KEY_FILE) {
        $env:ANTHROPIC_API_KEY_FILE
    }
    else {
        Join-Path $ROOT_DIR 'claudeapi.txt'
    }
    if (Test-Path -LiteralPath $anthropicKeyFile) {
        $env:ANTHROPIC_API_KEY = (Get-Content -LiteralPath $anthropicKeyFile -Raw).Trim()
    }
}

Test-RagCommand helm 'Install Helm, then open a new PowerShell window: winget install Helm.Helm, or choco install kubernetes-helm, or see https://helm.sh/docs/intro/install/'

function Test-RagTruthy {
    param([string]$Value)
    return $Value -match '^(1|true|yes|on)$'
}

function Test-RagRealBedrockBearerToken {
    if (-not $env:AWS_BEARER_TOKEN_BEDROCK) {
        return $false
    }
    return $env:AWS_BEARER_TOKEN_BEDROCK -ne 'replace-with-embedding-account-bedrock-api-key' -and
        $env:AWS_BEARER_TOKEN_BEDROCK -ne 'replace-with-bedrock-api-key'
}

function Test-RagRealGovInfoApiKey {
    if (-not $env:GOVINFO_API_KEY) {
        return $false
    }
    return $env:GOVINFO_API_KEY -ne 'replace-with-govinfo-api-key'
}

function Convert-RagRedisUrlForHelm {
    param([string]$RedisUrl)

    $url = if ($RedisUrl) { $RedisUrl.Trim() } else { '' }
    if (-not $url) {
        return 'redis://rag-redis-stack:6379'
    }

    # 127.0.0.1 / localhost inside a pod means the question-api container itself.
    # host.docker.internal targets the Docker Desktop host, not the Helm Redis service.
    # The Helm release installs Redis Stack as the in-cluster rag-redis-stack service.
    if ($url -match '^(?<scheme>rediss?)://(?<host>127\.0\.0\.1|localhost|host\.docker\.internal)(?<rest>(:\d+)?(/.*)?)$') {
        $scheme = $Matches.scheme
        $rest = $Matches.rest
        $path = ''
        if ($rest -match '(:\d+)?(?<path>/.*)$') {
            $path = $Matches.path
        }
        return "${scheme}://rag-redis-stack:6379$path"
    }

    return $url
}

$internalNetwork =
    (Test-RagTruthy $env:RAG_INTERNAL_NETWORK) -or
    (Test-RagTruthy $env:RAG_ON_PREM) -or
    (Test-RagTruthy $env:ON_PREM)
$awsCliAvailable = $null -ne (Get-Command aws -CommandType Application -ErrorAction SilentlyContinue)

$awsAuthMode = if ($env:AWS_AUTH_MODE) {
    $env:AWS_AUTH_MODE
}
elseif (Test-RagRealBedrockBearerToken) {
    'bearer'
}
elseif ($env:AWS_ACCESS_KEY_ID -or $env:AWS_SECRET_ACCESS_KEY -or $env:AWS_PROFILE -or $env:AWS_DEFAULT_PROFILE -or (-not $internalNetwork -and $awsCliAvailable)) {
    'accessKey'
}
elseif ($internalNetwork) {
    'none'
}
else {
    Write-Error @"
ERROR: Bedrock embedding credentials are required outside the internal/on-prem network.

Set one of:
  - AWS_BEARER_TOKEN_BEDROCK in .env
  - AWS_PROFILE / AWS_DEFAULT_PROFILE for an AWS CLI profile
  - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

For an internal/on-prem install that intentionally does not inject AWS credentials:
  `$env:RAG_INTERNAL_NETWORK = '1'; .\scripts\ps\Helm-Install.ps1
"@
    exit 1
}

if ($awsAuthMode -eq 'accessKey' -and (-not $env:AWS_ACCESS_KEY_ID -or -not $env:AWS_SECRET_ACCESS_KEY)) {
    Test-RagCommand aws 'Install AWS CLI v2 and run aws configure sso/login for the profile that can access the embedding model.'
    $awsProfile = if ($env:AWS_PROFILE) { $env:AWS_PROFILE } elseif ($env:AWS_DEFAULT_PROFILE) { $env:AWS_DEFAULT_PROFILE } else { '' }
    $exportArgs = @('configure', 'export-credentials', '--format', 'process')
    if ($awsProfile) {
        $exportArgs += @('--profile', $awsProfile)
    }
    $exported = & aws @exportArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host @"

AWS CLI could not export credentials (typical message: 'Unable to retrieve credentials: no credentials found').
Command: aws $($exportArgs -join ' ')

Fix one of:
  1. SSO: aws sso login --profile <name>   then set `$env:AWS_PROFILE` (or AWS_DEFAULT_PROFILE) and re-run.
  2. Keys: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (and AWS_SESSION_TOKEN if required) in .env or this session.
  3. Bearer: set AWS_BEARER_TOKEN_BEDROCK in .env (script uses aws.auth.mode=bearer).
  4. No AWS for this cluster: `$env:RAG_INTERNAL_NETWORK = '1'   then re-run (aws.auth.mode=none).

See README.md and .env.example.

"@ -ForegroundColor Yellow
        exit $LASTEXITCODE
    }
    $credentials = $exported | ConvertFrom-Json
    $env:AWS_ACCESS_KEY_ID = $credentials.AccessKeyId
    $env:AWS_SECRET_ACCESS_KEY = $credentials.SecretAccessKey
    if ($credentials.SessionToken) {
        $env:AWS_SESSION_TOKEN = $credentials.SessionToken
    }
}

$bedrockBearerTokenValue = if (Test-RagRealBedrockBearerToken) { $env:AWS_BEARER_TOKEN_BEDROCK } else { '' }
$govinfoApiKeyValue = if (Test-RagRealGovInfoApiKey) { $env:GOVINFO_API_KEY } else { 'DEMO_KEY' }
$retrievalTopK = Get-RagEnv -Name 'RETRIEVAL_TOP_K' -Default '5'
$retrievalScoreThreshold = Get-RagEnv -Name 'RETRIEVAL_SCORE_THRESHOLD' -Default '0.25'
$redisUrl = Convert-RagRedisUrlForHelm -RedisUrl (Get-RagEnv -Name 'LANGGRAPH_REDIS_URL' -Default (Get-RagEnv -Name 'REDIS_URL'))
$env:LANGGRAPH_REDIS_URL = $redisUrl
$novaSonicModelId = Get-RagEnv -Name 'BEDROCK_NOVA_SONIC_MODEL_ID' -Default (Get-RagEnv -Name 'NOVA_SONIC_MODEL' -Default 'amazon.nova-2-sonic-v1:0')
$novaSonicRoleArn = Get-RagEnv -Name 'SONIC_AWS_ROLE_ARN'
$novaSonicAccessKeyId = Get-RagEnv -Name 'SONIC_AWS_ACCESS_KEY_ID'
$novaSonicSecretAccessKey = Get-RagEnv -Name 'SONIC_AWS_SECRET_ACCESS_KEY'
$novaSonicSessionToken = Get-RagEnv -Name 'SONIC_AWS_SESSION_TOKEN'
$novaSonicCredentialExpiration = Get-RagEnv -Name 'SONIC_AWS_CREDENTIAL_EXPIRATION'

if (-not (Test-RagKubernetesNamespaceExists -Namespace $NAMESPACE)) {
    kubectl create namespace $NAMESPACE
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$argsList = @(
    'upgrade', '--install', $RELEASE,
    (Join-Path $ROOT_DIR 'infra/helm/rag-pgvector'),
    '--namespace', $NAMESPACE,
    '--create-namespace',
    '--set', 'fullnameOverride=rag',
    '--set', "image.tag=${TAG}",
    '--set', "aws.auth.mode=$awsAuthMode",
    '--set-string', "aws.auth.bearerToken=$bedrockBearerTokenValue",
    '--set-string', "aws.auth.accessKeyId=$(if ($env:AWS_ACCESS_KEY_ID) { $env:AWS_ACCESS_KEY_ID } else { '' })",
    '--set-string', "aws.auth.secretAccessKey=$(if ($env:AWS_SECRET_ACCESS_KEY) { $env:AWS_SECRET_ACCESS_KEY } else { '' })",
    '--set-string', "aws.auth.sessionToken=$(if ($env:AWS_SESSION_TOKEN) { $env:AWS_SESSION_TOKEN } else { '' })",
    '--set', "bedrock.region=$(if ($env:AWS_REGION) { $env:AWS_REGION } else { 'us-east-1' })",
    '--set-string', "bedrock.embeddingModelId=$(if ($env:EMBEDDING_MODEL) { $env:EMBEDDING_MODEL } elseif ($env:BEDROCK_EMBEDDING_MODEL_ID) { $env:BEDROCK_EMBEDDING_MODEL_ID } else { 'amazon.titan-embed-text-v2:0' })",
    '--set-string', "bedrock.embeddingBearerToken=$bedrockBearerTokenValue",
    '--set', "bedrock.embeddingDimensions=$(if ($env:BEDROCK_EMBEDDING_DIMENSIONS) { $env:BEDROCK_EMBEDDING_DIMENSIONS } else { '1024' })",
    '--set-string', "novaSonic.modelId=$novaSonicModelId",
    '--set-string', "novaSonic.roleArn=$novaSonicRoleArn",
    '--set-string', "novaSonic.accessKeyId=$novaSonicAccessKeyId",
    '--set-string', "novaSonic.secretAccessKey=$novaSonicSecretAccessKey",
    '--set-string', "novaSonic.sessionToken=$novaSonicSessionToken",
    '--set-string', "novaSonic.credentialExpiration=$novaSonicCredentialExpiration",
    '--set-string', "anthropic.apiKey=$(if ($env:ANTHROPIC_API_KEY) { $env:ANTHROPIC_API_KEY } else { '' })",
    '--set-string', "anthropic.model=$(if ($env:ANTHROPIC_DIRECT_MODEL) { $env:ANTHROPIC_DIRECT_MODEL } else { 'claude-sonnet-4-5' })",
    '--set', "anthropic.maxTokens=$(if ($env:ANTHROPIC_MAX_TOKENS) { $env:ANTHROPIC_MAX_TOKENS } else { '1024' })",
    '--set', "anthropic.temperature=$(if ($env:ANTHROPIC_TEMPERATURE) { $env:ANTHROPIC_TEMPERATURE } else { '0.0' })",
    '--set', "anthropic.timeoutSeconds=$(if ($env:ANTHROPIC_TIMEOUT_SECONDS) { $env:ANTHROPIC_TIMEOUT_SECONDS } else { '90' })",
    '--set-string', "govinfo.apiKey=$govinfoApiKeyValue",
    '--set-string', "govinfo.baseUrl=$(if ($env:GOVINFO_BASE_URL) { $env:GOVINFO_BASE_URL } else { 'https://api.govinfo.gov' })",
    '--set', "qa.topK=$retrievalTopK",
    '--set', "qa.scoreThreshold=$retrievalScoreThreshold",
    '--set-string', "vectorizer.env.LOG_LEVEL=$(Get-RagEnv -Name 'LOG_LEVEL' -Default 'DEBUG')",
    '--set-string', "vectorizer.env.LOG_FORMAT=$(Get-RagEnv -Name 'LOG_FORMAT' -Default 'json')",
    '--set-string', "qa.env.LOG_LEVEL=$(Get-RagEnv -Name 'LOG_LEVEL' -Default 'DEBUG')",
    '--set-string', "qa.env.LOG_FORMAT=$(Get-RagEnv -Name 'LOG_FORMAT' -Default 'json')",
    '--set-string', "qa.env.VOICE_ENABLED=$(Get-RagEnv -Name 'VOICE_ENABLED' -Default 'true')",
    '--set-string', "qa.env.NOVA_SONIC_VOICE=$(Get-RagEnv -Name 'NOVA_SONIC_VOICE' -Default 'matthew')",
    '--set-string', "qa.env.NOVA_SONIC_ENDPOINTING_SENSITIVITY=$(Get-RagEnv -Name 'NOVA_SONIC_ENDPOINTING_SENSITIVITY' -Default 'MEDIUM')",
    '--wait',
    '--timeout', '2m'
)

foreach ($envName in @('PGVECTOR_COLLECTION')) {
    $envValue = Get-RagEnv -Name $envName
    if ($envValue) {
        $argsList += @('--set-string', "vectorizer.env.$envName=$envValue")
        $argsList += @('--set-string', "qa.env.$envName=$envValue")
    }
}

foreach ($envName in @('LANGGRAPH_REDIS_URL', 'SESSION_CHECKPOINT_TTL_DAYS', 'SESSION_CHECKPOINT_TTL_REFRESH_ON_READ')) {
    $envValue = Get-RagEnv -Name $envName
    if ($envValue) {
        $argsList += @('--set-string', "qa.env.$envName=$envValue")
    }
}

if ($VALUES_FILE) {
    $argsList += @('-f', $VALUES_FILE)
}

Write-Host "helm upgrade --install $RELEASE <chart> --namespace $NAMESPACE --set image.tag=${TAG} --wait --timeout 2m"
& helm @argsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host @"

Release '$RELEASE' installed in namespace '$NAMESPACE'.
Run: .\scripts\ps\Port-Forward.ps1   or   .\scripts\ps\Rag.ps1 port-forward
"@
