param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$DeviceSerial = "",
    [int]$HealthPort = 18088,
    [switch]$SkipProxySmoke
)

$ErrorActionPreference = "Stop"

function Invoke-Adb {
    param([string[]]$Arguments)
    $base = @()
    if ($DeviceSerial) {
        $base += @("-s", $DeviceSerial)
    }
    $out = & "C:\Users\Bose\AppData\Local\Android\Sdk\platform-tools\adb.exe" @base @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($out -join [Environment]::NewLine)
    }
    return $out
}

function Get-RequiredEnv {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) {
        throw "Missing required environment variable: $Name"
    }
    return $value
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$manifest = Get-Content (Resolve-Path $ManifestPath) | ConvertFrom-Json

$adminToken = Get-RequiredEnv $manifest.tokens.adminTokenEnv
$relayUser = Get-RequiredEnv $manifest.tokens.relayUserEnv
$relayPassword = Get-RequiredEnv $manifest.tokens.relayPasswordEnv

Invoke-Adb @("forward", "tcp:$HealthPort", "tcp:8088") | Out-Null
$health = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers @{ Authorization = "Bearer $adminToken" }

if ($health.readiness_state -ne "healthy") {
    throw "Health check failed: readiness_state=$($health.readiness_state)"
}
if (-not $health.serving) {
    throw "Health check failed: serving=false"
}
if ($health.proxy_status -ne "running") {
    throw "Health check failed: proxy_status=$($health.proxy_status)"
}

if (-not $SkipProxySmoke) {
    & (Join-Path $repoRoot "scripts\test-public-proxy.ps1") -RelayHost $manifest.relay.host -Username $relayUser -Password $relayPassword | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Public proxy smoke test failed."
    }
}

Write-Output "Device verify passed: node=$($health.node_id) profile=$($health.active_operator_profile) ip=$($health.last_public_ip)"
