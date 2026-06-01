param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseId,
    [string]$DeviceSerial = "",
    [string]$DeviceRoot = "/data/adb/mobile-proxy-node",
    [string]$TempRoot = "/data/local/tmp/mobile-proxy-install",
    [string]$HostDaemonConfigPath = "",
    [string]$SingBoxConfigPath = "",
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

function Render-Template {
    param(
        [string]$Template,
        [hashtable]$Values
    )
    $rendered = $Template
    foreach ($key in $Values.Keys) {
        $token = "{{${key}}}"
        $rendered = $rendered.Replace($token, [string]$Values[$key])
    }
    return $rendered
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
$manifestFile = Resolve-Path $ManifestPath
$manifest = Get-Content $manifestFile | ConvertFrom-Json

$profileName = if ($manifest.operatorProfile) { [string]$manifest.operatorProfile } else { "default" }
$profilePath = Join-Path $repoRoot "deploy\device-runtime\profiles\$profileName.json"
if (-not (Test-Path $profilePath)) {
    throw "Profile not found: $profilePath"
}
$profile = Get-Content $profilePath | ConvertFrom-Json

$adminToken = Get-RequiredEnv $manifest.tokens.adminTokenEnv
$deviceToken = Get-RequiredEnv $manifest.tokens.deviceTokenEnv
$relayUser = Get-RequiredEnv $manifest.tokens.relayUserEnv
$relayPassword = Get-RequiredEnv $manifest.tokens.relayPasswordEnv

$binDir = Join-Path $repoRoot "deploy\device-runtime\bin"
$hostDaemonBin = Join-Path $binDir "host-daemon"
$singBoxBin = Join-Path $binDir "sing-box"
if (-not (Test-Path $hostDaemonBin)) {
    throw "Missing binary: $hostDaemonBin"
}
if (-not (Test-Path $singBoxBin)) {
    throw "Missing binary: $singBoxBin"
}

$stagingRoot = Join-Path $env:TEMP "mobile-proxy-runtime\$ReleaseId"
$releaseRoot = Join-Path $stagingRoot $ReleaseId
if (Test-Path $stagingRoot) {
    Remove-Item -Recurse -Force $stagingRoot
}
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "bin"), (Join-Path $releaseRoot "config") | Out-Null

Copy-Item (Join-Path $repoRoot "deploy\device-runtime\module\service.sh") (Join-Path $releaseRoot "service.sh")
Copy-Item (Join-Path $repoRoot "deploy\device-runtime\module\module.prop") (Join-Path $releaseRoot "module.prop")
Copy-Item $hostDaemonBin (Join-Path $releaseRoot "bin\host-daemon")
Copy-Item $singBoxBin (Join-Path $releaseRoot "bin\sing-box")

$hostRendered = $null
if ($HostDaemonConfigPath) {
    $hostRendered = Get-Content (Resolve-Path $HostDaemonConfigPath) -Raw
}
else {
    $hostTemplate = Get-Content (Join-Path $repoRoot "deploy\device-runtime\templates\host-daemon.base.json") -Raw
    $hostRendered = Render-Template -Template $hostTemplate -Values @{
        NODE_ID = [string]$manifest.deviceId
        NODE_NAME = [string]$manifest.nodeName
        ADMIN_TOKEN = $adminToken
        CONTROL_PLANE_URL = [string]$manifest.controlPlaneUrl
        DEVICE_TOKEN = $deviceToken
        OPERATOR_PROFILE = [string]$profile.operator_profile
        AIRPLANE_HOLD_SECS = [string]$profile.airplane_hold_secs
    }
}

$singBoxRendered = $null
if ($SingBoxConfigPath) {
    $singBoxRendered = Get-Content (Resolve-Path $SingBoxConfigPath) -Raw
}
else {
    $singBoxTemplate = Get-Content (Join-Path $repoRoot "deploy\device-runtime\templates\sing-box.base.json") -Raw
    $singBoxRendered = Render-Template -Template $singBoxTemplate -Values @{
        RELAY_USER = $relayUser
        RELAY_PASSWORD = $relayPassword
    }
}

Set-Content -Path (Join-Path $releaseRoot "config\host-daemon.json") -Value $hostRendered -NoNewline
Set-Content -Path (Join-Path $releaseRoot "config\sing-box.json") -Value $singBoxRendered -NoNewline

$checksumLines = @()
Get-ChildItem -Path $releaseRoot -Recurse -File | ForEach-Object {
    $hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLowerInvariant()
    $relative = $_.FullName.Substring($releaseRoot.Length + 1).Replace("\", "/")
    $checksumLines += "$hash *$relative"
}
Set-Content -Path (Join-Path $releaseRoot "checksums.sha256") -Value $checksumLines

$applyScript = @"
set -eu
ROOT='$DeviceRoot'
REL='$ReleaseId'
TMP='$TempRoot/$ReleaseId'
mkdir -p "`$ROOT/releases/`$REL"
cp -R "`$TMP/"* "`$ROOT/releases/`$REL/"
chmod +x "`$ROOT/releases/`$REL/service.sh" "`$ROOT/releases/`$REL/bin/host-daemon" "`$ROOT/releases/`$REL/bin/sing-box"
ln -sfn "`$ROOT/releases/`$REL" "`$ROOT/current"
sh "`$ROOT/current/service.sh"
"@

$applyLocal = Join-Path $stagingRoot "apply.sh"
Set-Content -Path $applyLocal -Value $applyScript -NoNewline

Invoke-Adb @("shell", "id") | Out-Null
$rootCheck = Invoke-Adb @("shell", "su", "0", "sh", "-c", "id")
if (-not (($rootCheck -join "`n") -match "uid=0")) {
    throw "Root access is required on device, but 'su -c id' did not return uid=0."
}

Invoke-Adb @("shell", "mkdir", "-p", "$TempRoot/$ReleaseId") | Out-Null
Invoke-Adb @("push", $releaseRoot, "$TempRoot") | Out-Null
Invoke-Adb @("push", $applyLocal, "$TempRoot/apply.sh") | Out-Null
Invoke-Adb @("shell", "su", "0", "sh", "-c", "sh $TempRoot/apply.sh") | Out-Null

Invoke-Adb @("forward", "tcp:$HealthPort", "tcp:8088") | Out-Null
$headers = @{ Authorization = "Bearer $adminToken" }
$health = $null
for ($attempt = 1; $attempt -le 40; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers $headers
        break
    }
    catch {
        if ($attempt -eq 40) {
            throw
        }
        Start-Sleep -Seconds 2
    }
}
$status = Get-EndpointJson -Uri "http://127.0.0.1:$HealthPort/v1/status" -Headers $headers
$proxy = Get-EndpointJson -Uri "http://127.0.0.1:$HealthPort/v1/proxy" -Headers $headers
if (-not $health.serving -or $health.readiness_state -ne "healthy") {
    $diag = @(
        "Post-install health check failed."
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
    throw ($diag -join [Environment]::NewLine)
}

if (-not $SkipProxySmoke) {
    & (Join-Path $repoRoot "scripts\test-public-proxy.ps1") -RelayHost $manifest.relay.host -Username $relayUser -Password $relayPassword | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Proxy smoke test failed after installation."
    }
}

Write-Output "Device runtime installed: release=$ReleaseId device=$($manifest.deviceId) readiness=$($health.readiness_state)"
