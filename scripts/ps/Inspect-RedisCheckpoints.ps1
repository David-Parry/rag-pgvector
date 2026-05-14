#requires -Version 5.1
<#
.SYNOPSIS
  Inspect Redis checkpoint keys and print their stored data.

.EXAMPLE
  .\scripts\ps\Inspect-RedisCheckpoints.ps1

.EXAMPLE
  .\scripts\ps\Inspect-RedisCheckpoints.ps1 -RedisCliPath "C:\Users\Ajit.Bandal\OneDrive - American Credit Acceptance (Technology)\Desktop\Desktop\Work\DCT\Redis-x64-5.0.10\redis-cli.exe"
#>
param(
    [string]$RedisUrl = 'redis://localhost:6379',
    [string]$Pattern = '*checkpoint:*',
    [string]$RedisCliPath = '',
    [int]$Limit = 0,
    [int]$Count = 200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

function Resolve-RedisCliPath {
    param([string]$Path)

    if ($Path) {
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "redis-cli was not found at '$Path'."
        }
        return (Resolve-Path -LiteralPath $Path).Path
    }

    $command = Get-Command redis-cli.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $command) {
        $command = Get-Command redis-cli -CommandType Application -ErrorAction SilentlyContinue
    }
    if (-not $command) {
        throw "redis-cli is not on PATH. Pass -RedisCliPath with the full path to redis-cli.exe."
    }

    return $command.Source
}

function Invoke-RedisCli {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $output = & $script:RedisCli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "redis-cli failed with exit code $LASTEXITCODE for arguments: $($Arguments -join ' ')"
    }
    return @($output)
}

function Get-RedisKeysByScan {
    param(
        [Parameter(Mandatory)][string]$RedisUrl,
        [Parameter(Mandatory)][string]$Pattern,
        [int]$Count = 200,
        [int]$Limit = 0
    )

    $keys = [System.Collections.Generic.List[string]]::new()
    $cursor = '0'

    do {
        $result = @(Invoke-RedisCli -Arguments @('-u', $RedisUrl, 'SCAN', $cursor, 'MATCH', $Pattern, 'COUNT', "$Count"))
        if (-not $result -or $result.Count -eq 0) {
            break
        }

        $cursor = [string]$result[0]
        foreach ($key in @($result | Select-Object -Skip 1)) {
            if ($key) {
                $null = $keys.Add([string]$key)
                if ($Limit -gt 0 -and $keys.Count -ge $Limit) {
                    return @($keys)
                }
            }
        }
    } while ($cursor -ne '0')

    return @($keys)
}

$script:RedisCli = Resolve-RedisCliPath -Path $RedisCliPath

Write-Host "Redis URL: $RedisUrl"
Write-Host "Pattern:   $Pattern"
Write-Host "CLI:       $script:RedisCli"

$keys = @(Get-RedisKeysByScan -RedisUrl $RedisUrl -Pattern $Pattern -Count $Count -Limit $Limit)

if (-not $keys -or $keys.Count -eq 0) {
    Write-Host "No keys matched '$Pattern'."
    exit 0
}

Write-Host "Matched keys: $($keys.Count)"

foreach ($key in $keys) {
    $type = (Invoke-RedisCli -Arguments @('-u', $RedisUrl, 'TYPE', $key) | Select-Object -First 1).Trim()
    $ttl = (Invoke-RedisCli -Arguments @('-u', $RedisUrl, 'TTL', $key) | Select-Object -First 1).Trim()

    Write-Host ""
    Write-Host "===== $key [$type] TTL=$ttl ====="

    switch ($type) {
        'string' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'GET', $key) | Write-Output
        }
        'hash' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'HGETALL', $key) | Write-Output
        }
        'list' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'LRANGE', $key, '0', '-1') | Write-Output
        }
        'set' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'SMEMBERS', $key) | Write-Output
        }
        'zset' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'ZRANGE', $key, '0', '-1', 'WITHSCORES') | Write-Output
        }
        'stream' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'XRANGE', $key, '-', '+') | Write-Output
        }
        'ReJSON-RL' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'JSON.GET', $key) | Write-Output
        }
        'ReJSON-RL2' {
            Invoke-RedisCli -Arguments @('-u', $RedisUrl, '--raw', 'JSON.GET', $key) | Write-Output
        }
        default {
            Write-Host "Unsupported or missing Redis type: $type"
        }
    }
}
