#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$EnvFile = Join-Path $RootDir ".env"
$DockerDesktopScript = Join-Path $ScriptDir "Docker-Desktop-Up.ps1"

. "$ScriptDir/_Common.ps1"

function Get-PipIndexUrl {
    $candidatePaths = @()
    if ($env:APPDATA) {
        $candidatePaths += (Join-Path $env:APPDATA "pip\pip.ini")
    }
    if ($env:USERPROFILE) {
        $candidatePaths += (Join-Path $env:USERPROFILE "pip\pip.ini")
    }

    foreach ($path in $candidatePaths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            continue
        }

        $line = Select-String -LiteralPath $path -Pattern '^\s*index-url\s*=\s*(.+?)\s*$' |
            Select-Object -First 1
        if ($line) {
            return $line.Matches[0].Groups[1].Value.Trim()
        }
    }

    return $null
}

Import-RagDotEnv -Path $EnvFile

$createdSecretFile = $false
if ($env:RAG_UV_DEFAULT_INDEX_FILE) {
    if (-not (Test-Path -LiteralPath $env:RAG_UV_DEFAULT_INDEX_FILE -PathType Leaf)) {
        throw "RAG_UV_DEFAULT_INDEX_FILE points to a missing file: $($env:RAG_UV_DEFAULT_INDEX_FILE)"
    }
}
else {
    $indexUrl = if ($env:RAG_DOCKER_UV_DEFAULT_INDEX) {
        $env:RAG_DOCKER_UV_DEFAULT_INDEX
    }
    else {
        Get-PipIndexUrl
    }

    if (-not $indexUrl) {
        throw "No Artifactory/PyPI index found. Set RAG_UV_DEFAULT_INDEX_FILE or configure index-url in pip.ini."
    }

    if ($indexUrl -notmatch '/simple/?$') {
        $indexUrl = $indexUrl.TrimEnd('/') + '/simple'
    }

    $secretFile = Join-Path $env:TEMP 'rag-pgvector-uv-default-index.txt'
    [System.IO.File]::WriteAllText($secretFile, $indexUrl)
    $env:RAG_UV_DEFAULT_INDEX_FILE = $secretFile
    $createdSecretFile = $true
}

try {
    & $DockerDesktopScript
    exit $LASTEXITCODE
}
finally {
    if ($createdSecretFile) {
        Remove-Item -LiteralPath $env:RAG_UV_DEFAULT_INDEX_FILE -Force -ErrorAction SilentlyContinue
    }
}
 