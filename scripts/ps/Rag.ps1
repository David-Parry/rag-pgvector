#requires -Version 5.1
<#
.SYNOPSIS
  Dispatcher for rag-pgvector PowerShell scripts (Windows counterpart to scripts/*.sh).

.EXAMPLE
  .\Rag.ps1 docker-up
  .\Rag.ps1 helm-install
  .\Rag.ps1 port-forward
  .\Rag.ps1 ingest-package BILLS-115hr1625enr
  .\Rag.ps1 ask "your question"
  .\Rag.ps1 seed-ingest
  .\Rag.ps1 bedrock-create-api-key
  .\Rag.ps1 bedrock-smoke
  .\Rag.ps1 teardown

.EXAMPLE
  $env:KILL_STALE = '1'; .\Rag.ps1 port-forward
#>
param(
    [Parameter(Position = 0)]
    [string]$Command,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-RagUsage {
    Write-Host @'
rag-pgvector - PowerShell helper

Usage:
  .\Rag.ps1 <command> [arguments...]

Commands:
  docker-up              Build images and prep Docker Desktop Kubernetes namespace
  helm-install           helm upgrade --install (loads repo .env)
  port-forward           kubectl port-forward vectorizer, question-api, postgres
  ingest-package <id>    POST /ingest/package
  ask [question]         POST /ask (omit question for demo default)
  seed-ingest            POST /ingest sample batch
  bedrock-create-api-key AWS IAM + Bedrock key -> .env
  bedrock-smoke [text]   Embed smoke test using bearer token in .env
  teardown               helm uninstall + optional namespace delete

Environment variables match the bash scripts (e.g. NAMESPACE, TAG, VECTORIZER_URL).

Examples:
  .\Rag.ps1 docker-up
  .\Rag.ps1 ingest-package BILLS-115hr1625enr
  $env:RAW='1'; .\Rag.ps1 ask "short question"

Individual scripts live beside this file:
  Docker-Desktop-Up.ps1, Helm-Install.ps1, Port-Forward.ps1, ...
'@
}

if (-not $Command) {
    Write-RagUsage
    exit 2
}

if ($Command -eq 'help' -or $Command -eq '-h' -or $Command -eq '--help') {
    Write-RagUsage
    exit 0
}

$here = $PSScriptRoot
$forwardArgs = @()
if ($RemainingArgs -and $RemainingArgs.Count -gt 0) {
    $forwardArgs = $RemainingArgs
}

switch -Regex ($Command.ToLowerInvariant()) {
    '^docker-up$|^docker-desktop-up$' {
        & (Join-Path $here 'Docker-Desktop-Up.ps1') @forwardArgs
        break
    }
    '^helm-install$|^helm$' {
        & (Join-Path $here 'Helm-Install.ps1') @forwardArgs
        break
    }
    '^port-forward$|^pf$' {
        & (Join-Path $here 'Port-Forward.ps1') @forwardArgs
        break
    }
    '^ingest-package$|^ingest$' {
        & (Join-Path $here 'Ingest-Package.ps1') @forwardArgs
        break
    }
    '^ask$' {
        if ($forwardArgs.Count -eq 0) {
            & (Join-Path $here 'Ask.ps1')
        }
        else {
            $joined = ($forwardArgs -join ' ').Trim()
            & (Join-Path $here 'Ask.ps1') $joined
        }
        break
    }
    '^seed-ingest$|^seed$' {
        & (Join-Path $here 'Seed-Ingest.ps1') @forwardArgs
        break
    }
    '^bedrock-create-api-key$|^bedrock-key$' {
        & (Join-Path $here 'Bedrock-Create-ApiKey.ps1') @forwardArgs
        break
    }
    '^bedrock-smoke$' {
        & (Join-Path $here 'Bedrock-Smoke.ps1') @forwardArgs
        break
    }
    '^teardown$|^down$' {
        & (Join-Path $here 'Teardown.ps1') @forwardArgs
        break
    }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ''
        Write-RagUsage
        exit 2
    }
}
