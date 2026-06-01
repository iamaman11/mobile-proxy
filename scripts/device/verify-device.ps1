param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$DeviceSerial = "",
    [int]$HealthPort = 18088,
    [switch]$SkipProxySmoke
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Invoke-Adb {
    param([string[]]$Arguments)
    $base = @()
    if ($DeviceSerial) {
        $base += @("-s", $DeviceSerial)
    }
    $all = @($base + $Arguments)
    $stdoutPath = Join-Path $env:TEMP ("adb-out-" + [guid]::NewGuid().ToString() + ".log")
    $stderrPath = Join-Path $env:TEMP ("adb-err-" + [guid]::NewGuid().ToString() + ".log")
    try {
        $proc = Start-Process -FilePath "C:\Users\Bose\AppData\Local\Android\Sdk\platform-tools\adb.exe" `
            -ArgumentList $all `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath
        $stdout = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -ErrorAction SilentlyContinue } else { @() }
        $stderr = if (Test-Path $stderrPath) { Get-Content $stderrPath -ErrorAction SilentlyContinue } else { @() }
        if ($proc.ExitCode -ne 0) {
            $message = @($stdout + $stderr) -join [Environment]::NewLine
            throw $message
        }
        return @($stdout + $stderr)
    }
    finally {
        Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-RequiredEnv {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) {
        throw "Missing required environment variable: $Name"
    }
    return $value
}

function Get-EndpointJson {
    param(
        [string]$Uri,
        [hashtable]$Headers
    )
    try {
        return Invoke-RestMethod -Uri $Uri -Headers $Headers
    }
    catch {
        return $null
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$manifest = Get-Content (Resolve-Path $ManifestPath) | ConvertFrom-Json

$adminToken = Get-RequiredEnv $manifest.tokens.adminTokenEnv
$relayUser = Get-RequiredEnv $manifest.tokens.relayUserEnv
$relayPassword = Get-RequiredEnv $manifest.tokens.relayPasswordEnv

Invoke-Adb @("forward", "tcp:$HealthPort", "tcp:8088") | Out-Null
$headers = @{ Authorization = "Bearer $adminToken" }
$health = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers $headers
$status = Get-EndpointJson -Uri "http://127.0.0.1:$HealthPort/v1/status" -Headers $headers
$proxy = Get-EndpointJson -Uri "http://127.0.0.1:$HealthPort/v1/proxy" -Headers $headers
$packages = Invoke-Adb @("shell", "pm", "list", "packages", "com.wireguard.android")
$wireguardInstalled = (($packages -join "`n") -match "com.wireguard.android")

$healthy = ($health.readiness_state -eq "healthy") -and $health.serving -and ($health.proxy_status -eq "running")
if (-not $healthy) {
    $diag = @(
        "Health check failed."
        "readiness_state=$($health.readiness_state)"
        "serving=$($health.serving)"
        "proxy_status=$($health.proxy_status)"
        "serving_failure_reason=$($health.serving_failure_reason)"
        "degradation_reason_code=$($health.degradation_reason_code)"
        "last_proxy_error=$($health.last_proxy_error)"
        "tun0_present=$($health.tun0_present)"
        "wg_handshake_recent=$($health.wg_handshake_recent)"
        "proxy_bind_ready=$($health.proxy_bind_ready)"
    )
    if ($status) {
        $diag += "wireguard_enabled=$($status.wireguard_enabled)"
    }
    if ($proxy) {
        $diag += "proxy.listen_address=$($proxy.listen_address)"
    }
    if (-not $wireguardInstalled) {
        $diag += "wireguard_app_installed=false (package com.wireguard.android missing)"
    }
    throw ($diag -join [Environment]::NewLine)
}

if (-not $SkipProxySmoke) {
    & (Join-Path $repoRoot "scripts\test-public-proxy.ps1") -RelayHost $manifest.relay.host -Username $relayUser -Password $relayPassword | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Public proxy smoke test failed."
    }
}

Write-Output "Device verify passed: node=$($health.node_id) profile=$($health.active_operator_profile) ip=$($health.last_public_ip)"
