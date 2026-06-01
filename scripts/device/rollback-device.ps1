param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$ReleaseId = "",
    [string]$DeviceSerial = "",
    [string]$DeviceRoot = "/data/adb/mobile-proxy-node",
    [int]$HealthPort = 18088
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

$manifest = Get-Content (Resolve-Path $ManifestPath) | ConvertFrom-Json
$adminToken = Get-RequiredEnv $manifest.tokens.adminTokenEnv

$rootCheck = Invoke-Adb @("shell", "su", "0", "sh", "-c", "id")
if (-not (($rootCheck -join "`n") -match "uid=0")) {
    throw "Root access is required on device for rollback."
}

$current = (Invoke-Adb @("shell", "su", "0", "sh", "-c", "readlink $DeviceRoot/current")).Trim()
$currentRelease = [System.IO.Path]::GetFileName($current)
$releases = (Invoke-Adb @("shell", "su", "0", "sh", "-c", "ls -1t $DeviceRoot/releases")).Where({ $_.Trim() -ne "" })
if (-not $releases -or $releases.Count -eq 0) {
    throw "No releases found under $DeviceRoot/releases."
}

$targetRelease = $ReleaseId
if (-not $targetRelease) {
    $targetRelease = ($releases | Where-Object { $_ -ne $currentRelease } | Select-Object -First 1)
}

if (-not $targetRelease) {
    throw "Could not select rollback target release."
}

$switchCmd = "set -eu; ln -sfn $DeviceRoot/releases/$targetRelease $DeviceRoot/current; sh $DeviceRoot/current/service.sh"
Invoke-Adb @("shell", "su", "0", "sh", "-c", $switchCmd) | Out-Null

Invoke-Adb @("forward", "tcp:$HealthPort", "tcp:8088") | Out-Null
$health = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers @{ Authorization = "Bearer $adminToken" }
if (-not $health.serving -or $health.readiness_state -ne "healthy") {
    throw "Rollback health check failed: readiness=$($health.readiness_state) serving=$($health.serving)"
}

Write-Output "Rollback applied: current=$targetRelease readiness=$($health.readiness_state)"
