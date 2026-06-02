param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$DeviceSerial = "",
    [string]$Strategy = "airplane_bounce",
    [string]$Reason = "manual-rotate",
    [bool]$RequirePublicIpChange = $true,
    [int]$HealthPort = 18088,
    [int]$TimeoutSeconds = 300,
    [int]$RepairAfterSeconds = 45,
    [int]$RestartAfterSeconds = 120,
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

function Repair-CellularDefaultRoute {
    $line = (Invoke-Adb @("shell", "su", "0", "sh", "-c", "ip -4 route get 1.1.1.1 2>/dev/null | head -n1")) -join " "
    if (-not $line) {
        $line = (Invoke-Adb @(
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            "ip -4 route show table all 2>/dev/null | grep -E '^default .* dev (rmnet|ccmni|pdp|wwan)[0-9]*' | head -n1"
        )) -join " "
    }
    if (-not $line) {
        $devLine = (Invoke-Adb @(
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            "ip -o link show 2>/dev/null | grep -E '(rmnet|ccmni|pdp|wwan)' | grep 'UP' | head -n1"
        )) -join " "
        if ($devLine -match "^\d+:\s*([^:]+):") {
            $line = "default dev $($Matches[1])"
        }
    }
    if (-not $line) {
        return
    }
    $dev = ""
    $via = ""
    if ($line -match "\bdev\s+([^\s]+)") {
        $dev = $Matches[1]
    }
    if ($line -match "\bvia\s+([^\s]+)") {
        $via = $Matches[1]
    }
    if (-not $dev) {
        return
    }
    if ($dev -notmatch "^(rmnet|ccmni|pdp|wwan)") {
        return
    }

    $cmd = if ($via) { "ip route replace default via $via dev $dev" } else { "ip route replace default dev $dev" }
    Invoke-Adb @("shell", "su", "0", "sh", "-c", $cmd) | Out-Null
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$manifest = Get-Content (Resolve-Path $ManifestPath) | ConvertFrom-Json

$adminToken = Get-RequiredEnv $manifest.tokens.adminTokenEnv
$relayUser = Get-RequiredEnv $manifest.tokens.relayUserEnv
$relayPassword = Get-RequiredEnv $manifest.tokens.relayPasswordEnv

Invoke-Adb @("forward", "tcp:$HealthPort", "tcp:8088") | Out-Null
$headers = @{ Authorization = "Bearer $adminToken" }

$healthBefore = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers $headers
$beforeIp = $healthBefore.last_public_ip

$payload = @{
    strategy = $Strategy
    require_public_ip_change = $RequirePublicIpChange
    reason = $Reason
} | ConvertTo-Json -Compress

$jobId = $null
try {
    $accepted = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HealthPort/v1/ip/rotate" -Headers $headers -ContentType "application/json" -Body $payload
    $jobId = $accepted.job_id
}
catch {
    $responseText = $_.ErrorDetails.Message
    if ($responseText -match "another job is already running") {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/status" -Headers $headers
        if (-not $status.current_job) {
            throw "Rotation request rejected and no current job id is present."
        }
        $jobId = $status.current_job
    }
    else {
        throw
    }
}

$startedAt = Get-Date
$routeRepaired = $false
$runtimeRestarted = $false
$job = $null

while ($true) {
    $elapsed = [int]((Get-Date) - $startedAt).TotalSeconds
    if ($elapsed -gt $TimeoutSeconds) {
        throw "Rotation timeout: job=$jobId exceeded ${TimeoutSeconds}s"
    }

    $job = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/jobs/$jobId" -Headers $headers
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers $headers
    Write-Output ("{0} job={1} readiness={2} serving={3} route_ready={4} ip={5}" -f (Get-Date -Format HH:mm:ss), $job.status, $health.readiness_state, $health.serving, $health.cellular_route_ready, $health.last_public_ip)

    if (-not $routeRepaired -and $elapsed -ge $RepairAfterSeconds -and $health.readiness_state -eq "waiting_cellular") {
        Repair-CellularDefaultRoute
        $routeRepaired = $true
        Write-Output "Applied cellular default route repair."
    }

    if (-not $runtimeRestarted -and $elapsed -ge $RestartAfterSeconds -and (-not $health.serving)) {
        Invoke-Adb @("shell", "su", "0", "sh", "-c", "sh /data/adb/mobile-proxy-node/current/service.sh") | Out-Null
        $runtimeRestarted = $true
        Write-Output "Restarted runtime service."
    }

    if ($job.status -ne "running") {
        break
    }

    Start-Sleep -Seconds 2
}

if ($job.status -ne "succeeded") {
    $rendered = $job | ConvertTo-Json -Depth 8
    throw "Rotation failed: $rendered"
}

$finalHealth = $null
$postRepairApplied = $false
$postRestartApplied = $false
for ($i = 0; $i -lt 60; $i++) {
    $finalHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$HealthPort/v1/health" -Headers $headers
    if ($finalHealth.readiness_state -eq "healthy" -and $finalHealth.serving) {
        break
    }
    if (-not $postRepairApplied -and $finalHealth.readiness_state -eq "waiting_cellular") {
        Repair-CellularDefaultRoute
        $postRepairApplied = $true
        Write-Output "Applied post-rotate route repair."
    }
    if (-not $postRestartApplied -and $i -ge 20 -and -not $finalHealth.serving) {
        Invoke-Adb @("shell", "su", "0", "sh", "-c", "sh /data/adb/mobile-proxy-node/current/service.sh") | Out-Null
        $postRestartApplied = $true
        Write-Output "Applied post-rotate runtime restart."
    }
    Start-Sleep -Seconds 2
}

if ($finalHealth.readiness_state -ne "healthy" -or -not $finalHealth.serving) {
    throw "Rotation finished but runtime is not healthy: readiness=$($finalHealth.readiness_state) serving=$($finalHealth.serving)"
}

$afterIp = $finalHealth.last_public_ip
if ($RequirePublicIpChange) {
    if (-not $beforeIp -or -not $afterIp -or $beforeIp -eq $afterIp) {
        throw "Public IP did not change: before=$beforeIp after=$afterIp"
    }
}

if (-not $SkipProxySmoke) {
    & (Join-Path $repoRoot "scripts\test-public-proxy.ps1") -RelayHost $manifest.relay.host -Username $relayUser -Password $relayPassword | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Public proxy smoke test failed after rotation."
    }
}

Write-Output "Rotate passed: job=$jobId before=$beforeIp after=$afterIp strategy=$Strategy"
