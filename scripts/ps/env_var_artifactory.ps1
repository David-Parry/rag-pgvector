#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$EnvFile = Join-Path $RootDir ".env"
$DockerDesktopScript = Join-Path $ScriptDir "Docker-Desktop-Up.ps1"

. "$ScriptDir/_Common.ps1"

function Get-PipIniCandidatePaths {
    $paths = [System.Collections.Generic.List[string]]::new()
    if ($env:APPDATA) {
        $null = $paths.Add((Join-Path $env:APPDATA "pip\pip.ini"))
    }
    if ($env:USERPROFILE) {
        $null = $paths.Add((Join-Path $env:USERPROFILE "pip\pip.ini"))
    }
    if ($env:ProgramData) {
        $null = $paths.Add((Join-Path $env:ProgramData "pip\pip.ini"))
    }
    return @($paths | Where-Object { $_ } | Select-Object -Unique)
}

function Read-IndexUrlFromPipIniFile {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath
    )
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        return $null
    }
    $raw = Get-Content -LiteralPath $FilePath -Raw -ErrorAction Stop
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    $raw = $raw.TrimStart([char]0xFEFF)
    foreach ($line in ($raw -split "`r?`n")) {
        $t = $line.TrimEnd("`r")
        if ($t -match '(?i)^\s*index-url\s*=\s*(.+)$') {
            $val = $Matches[1].Trim()
            if ($val.StartsWith('"') -and $val.EndsWith('"') -and $val.Length -ge 2) {
                $val = $val.Substring(1, $val.Length - 2).Trim()
            }
            elseif ($val.StartsWith("'") -and $val.EndsWith("'") -and $val.Length -ge 2) {
                $val = $val.Substring(1, $val.Length - 2).Trim()
            }
            $hash = $val.IndexOf('#')
            if ($hash -ge 0) {
                $val = $val.Substring(0, $hash).Trim()
            }
            if ($val) {
                return $val
            }
        }
    }
    return $null
}

function Get-PipIndexUrl {
    foreach ($path in Get-PipIniCandidatePaths) {
        $url = Read-IndexUrlFromPipIniFile -FilePath $path
        if ($url) {
            return $url
        }
    }
    return $null
}

function Get-PipIniPathWithIndexUrl {
    foreach ($path in Get-PipIniCandidatePaths) {
        if (Read-IndexUrlFromPipIniFile -FilePath $path) {
            return $path
        }
    }
    return $null
}

function Ensure-Pep503SimpleSuffix {
    param([string]$Url)
    if ($Url -notmatch '/simple/?$') {
        return $Url.TrimEnd('/') + '/simple'
    }
    return $Url
}

function Set-IndexUrlForDockerBuild {
    param(
        [Parameter(Mandatory)]
        [string]$IndexUrl
    )
    $normalized = Ensure-Pep503SimpleSuffix -Url $IndexUrl
    if (-not $env:RAG_DOCKER_PIP_INDEX_URL -and -not $env:RAG_DOCKER_UV_DEFAULT_INDEX) {
        $env:RAG_DOCKER_PIP_INDEX_URL = $normalized
    }
    if (-not $env:RAG_PIP_INDEX_URL_FILE -and -not $env:RAG_UV_DEFAULT_INDEX_FILE) {
        $secretFile = Join-Path $env:TEMP 'rag-pgvector-pip-index-url.txt'
        [System.IO.File]::WriteAllText($secretFile, $normalized)
        $env:RAG_PIP_INDEX_URL_FILE = $secretFile
        return $secretFile
    }
    return $null
}

Import-RagDotEnv -Path $EnvFile

$createdSecretFile = $false
$pipSecretPath = $env:RAG_PIP_INDEX_URL_FILE
$uvSecretPath = $env:RAG_UV_DEFAULT_INDEX_FILE

$existingSecretFile = $null
if ($pipSecretPath -and (Test-Path -LiteralPath $pipSecretPath -PathType Leaf)) {
    $existingSecretFile = $pipSecretPath
}
elseif ($uvSecretPath -and (Test-Path -LiteralPath $uvSecretPath -PathType Leaf)) {
    $existingSecretFile = $uvSecretPath
}
elseif ($pipSecretPath -or $uvSecretPath) {
    Write-Warning @"
RAG_PIP_INDEX_URL_FILE or RAG_UV_DEFAULT_INDEX_FILE points to a file that does not exist (often a stale temp path after a prior run). Remove those variables from .env or your session, or point them to a real file. Resolving the index from RAG_DOCKER_PIP_INDEX_URL / RAG_DOCKER_UV_DEFAULT_INDEX or pip.ini instead.
"@
    Remove-Item Env:\RAG_PIP_INDEX_URL_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:\RAG_UV_DEFAULT_INDEX_FILE -ErrorAction SilentlyContinue
}

if ($existingSecretFile) {
    $env:RAG_PIP_INDEX_URL_FILE = $existingSecretFile
    $urlFromOneLine = Get-Content -LiteralPath $existingSecretFile -Raw
    if ($urlFromOneLine) {
        $trimUrl = ($urlFromOneLine -split "`r?`n")[0].Trim()
        if ($trimUrl -and -not $env:RAG_DOCKER_PIP_INDEX_URL -and -not $env:RAG_DOCKER_UV_DEFAULT_INDEX) {
            $env:RAG_DOCKER_PIP_INDEX_URL = Ensure-Pep503SimpleSuffix -Url $trimUrl
        }
    }
}
else {
    $pipConfigForDocker = $null
    if ($env:RAG_DOCKER_PIP_CONFIG_FILE) {
        if (Test-Path -LiteralPath $env:RAG_DOCKER_PIP_CONFIG_FILE -PathType Leaf) {
            $pipConfigForDocker = $env:RAG_DOCKER_PIP_CONFIG_FILE
        }
        else {
            Write-Warning "RAG_DOCKER_PIP_CONFIG_FILE points to a missing file: $($env:RAG_DOCKER_PIP_CONFIG_FILE)"
        }
    }
    if (-not $pipConfigForDocker) {
        $discoveredIni = Get-PipIniPathWithIndexUrl
        if ($discoveredIni) {
            $pipConfigForDocker = $discoveredIni
            $env:RAG_DOCKER_PIP_CONFIG_FILE = $discoveredIni
        }
    }

    if ($pipConfigForDocker) {
        $fromIni = Read-IndexUrlFromPipIniFile -FilePath $pipConfigForDocker
        if ($fromIni) {
            $tempPath = Set-IndexUrlForDockerBuild -IndexUrl $fromIni
            if ($tempPath) {
                $createdSecretFile = $true
            }
        }
        else {
            Write-Warning @"
RAG_DOCKER_PIP_CONFIG_FILE ($pipConfigForDocker) has no readable index-url= line. Docker will still receive pip_config as /etc/pip.conf; set RAG_DOCKER_PIP_INDEX_URL or add index-url under [global] in that file.
"@
        }
    }
    else {
        $indexUrl = if ($env:RAG_DOCKER_PIP_INDEX_URL) {
            $env:RAG_DOCKER_PIP_INDEX_URL
        }
        elseif ($env:RAG_DOCKER_UV_DEFAULT_INDEX) {
            $env:RAG_DOCKER_UV_DEFAULT_INDEX
        }
        else {
            Get-PipIndexUrl
        }

        if (-not $indexUrl) {
            throw "No Artifactory/PyPI index found. Set RAG_DOCKER_PIP_CONFIG_FILE to your pip.ini, RAG_PIP_INDEX_URL_FILE (or legacy RAG_UV_DEFAULT_INDEX_FILE), RAG_DOCKER_PIP_INDEX_URL / RAG_DOCKER_UV_DEFAULT_INDEX, or configure index-url in pip.ini (for example under %APPDATA%\pip\pip.ini)."
        }

        $normalized = Ensure-Pep503SimpleSuffix -Url $indexUrl
        $secretFile = Join-Path $env:TEMP 'rag-pgvector-pip-index-url.txt'
        [System.IO.File]::WriteAllText($secretFile, $normalized)
        $env:RAG_PIP_INDEX_URL_FILE = $secretFile
        if (-not $env:RAG_DOCKER_PIP_INDEX_URL -and -not $env:RAG_DOCKER_UV_DEFAULT_INDEX) {
            $env:RAG_DOCKER_PIP_INDEX_URL = $normalized
        }
        $createdSecretFile = $true
    }
}

try {
    & $DockerDesktopScript
    exit $LASTEXITCODE
}
finally {
    if ($createdSecretFile -and $env:RAG_PIP_INDEX_URL_FILE) {
        Remove-Item -LiteralPath $env:RAG_PIP_INDEX_URL_FILE -Force -ErrorAction SilentlyContinue
    }
}
