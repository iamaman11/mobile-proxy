param(
    [string]$ProjectRoot = "\\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy",
    [string]$Token = "replace_me"
)

$ErrorActionPreference = "Stop"
$targetDir = Join-Path $ProjectRoot ".run"
$logDir = Join-Path $targetDir "logs"
$binDir = Join-Path $ProjectRoot "target\debug"
New-Item -ItemType Directory -Force -Path $targetDir, $logDir | Out-Null

$hostDaemonOut = Join-Path $logDir "host-daemon.out.log"
$hostDaemonErr = Join-Path $logDir "host-daemon.err.log"
$controlPlaneOut = Join-Path $logDir "control-plane.out.log"
$controlPlaneErr = Join-Path $logDir "control-plane.err.log"
$relayGateOut = Join-Path $logDir "relay-gate.out.log"
$relayGateErr = Join-Path $logDir "relay-gate.err.log"

Get-Process host-daemon, control-plane, relay-gate -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Process -FilePath (Join-Path $binDir "control-plane.exe") -RedirectStandardOutput $controlPlaneOut -RedirectStandardError $controlPlaneErr -WindowStyle Hidden -WorkingDirectory $ProjectRoot | Out-Null
Start-Sleep 1

$previousListen = $env:HOST_DAEMON_LISTEN
$previousToken = $env:HOST_DAEMON_ADMIN_TOKEN
$previousNodeId = $env:HOST_DAEMON_NODE_ID
$previousNodeName = $env:HOST_DAEMON_NODE_NAME
$previousFingerprint = $env:HOST_DAEMON_BINARY_FINGERPRINT
$previousControlPlaneUrl = $env:HOST_DAEMON_CONTROL_PLANE_URL
$env:HOST_DAEMON_LISTEN = "127.0.0.1:8088"
$env:HOST_DAEMON_ADMIN_TOKEN = $Token
$env:HOST_DAEMON_NODE_ID = "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06"
$env:HOST_DAEMON_NODE_NAME = "galaxy-a02-gcp-relay"
$env:HOST_DAEMON_BINARY_FINGERPRINT = "local-dev"
$env:HOST_DAEMON_CONTROL_PLANE_URL = "http://127.0.0.1:8080"
Start-Process -FilePath (Join-Path $binDir "host-daemon.exe") -RedirectStandardOutput $hostDaemonOut -RedirectStandardError $hostDaemonErr -WindowStyle Hidden -WorkingDirectory $ProjectRoot | Out-Null
if ($null -eq $previousListen) { Remove-Item Env:HOST_DAEMON_LISTEN -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_LISTEN = $previousListen }
if ($null -eq $previousToken) { Remove-Item Env:HOST_DAEMON_ADMIN_TOKEN -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_ADMIN_TOKEN = $previousToken }
if ($null -eq $previousNodeId) { Remove-Item Env:HOST_DAEMON_NODE_ID -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_NODE_ID = $previousNodeId }
if ($null -eq $previousNodeName) { Remove-Item Env:HOST_DAEMON_NODE_NAME -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_NODE_NAME = $previousNodeName }
if ($null -eq $previousFingerprint) { Remove-Item Env:HOST_DAEMON_BINARY_FINGERPRINT -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_BINARY_FINGERPRINT = $previousFingerprint }
if ($null -eq $previousControlPlaneUrl) { Remove-Item Env:HOST_DAEMON_CONTROL_PLANE_URL -ErrorAction SilentlyContinue } else { $env:HOST_DAEMON_CONTROL_PLANE_URL = $previousControlPlaneUrl }
Start-Sleep 1

$previousCpUrl = $env:CONTROL_PLANE_URL
$previousRelayId = $env:RELAY_GATE_DEVICE_ID
$previousRelayUpstream = $env:RELAY_GATE_UPSTREAM
$env:CONTROL_PLANE_URL = "http://127.0.0.1:8080"
$env:RELAY_GATE_DEVICE_ID = "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06"
$env:RELAY_GATE_UPSTREAM = "127.0.0.1:8088"
Start-Process -FilePath (Join-Path $binDir "relay-gate.exe") -RedirectStandardOutput $relayGateOut -RedirectStandardError $relayGateErr -WindowStyle Hidden -WorkingDirectory $ProjectRoot | Out-Null
if ($null -eq $previousCpUrl) { Remove-Item Env:CONTROL_PLANE_URL -ErrorAction SilentlyContinue } else { $env:CONTROL_PLANE_URL = $previousCpUrl }
if ($null -eq $previousRelayId) { Remove-Item Env:RELAY_GATE_DEVICE_ID -ErrorAction SilentlyContinue } else { $env:RELAY_GATE_DEVICE_ID = $previousRelayId }
if ($null -eq $previousRelayUpstream) { Remove-Item Env:RELAY_GATE_UPSTREAM -ErrorAction SilentlyContinue } else { $env:RELAY_GATE_UPSTREAM = $previousRelayUpstream }
Start-Sleep 2

Write-Output "local stack started"
Write-Output "host-daemon:   http://127.0.0.1:8088"
Write-Output "control-plane: http://127.0.0.1:8080"
Write-Output "logs:          $logDir"
