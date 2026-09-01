<#
.SYNOPSIS
    Installs the per-user Windows logon bridge for the approved production-phone USB bus.
#>
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu',
    [string]$HardwareId = '04e8:6860',
    [string]$InstallRoot = 'C:\ProgramData\MobileProxy\usb-bridge'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command usbipd.exe -ErrorAction SilentlyContinue)) { throw 'usbipd unavailable' }
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'wsl unavailable' }

$rows = @(& usbipd.exe list 2>$null | Select-Object -Skip 1 | Where-Object { $_ -match "^\s*\d+-\d+\s+$([regex]::Escape($HardwareId))\s+" })
if ($rows.Count -ne 1) { throw 'Expected exactly one approved Samsung USB device; refusing ambiguous installation.' }
if ($rows[0] -notmatch '^\s*([0-9-]+)\s+') { throw 'Could not determine approved USB bus.' }
$busId = $Matches[1]

$source = Join-Path $PSScriptRoot 'mobile-proxy-usb-bridge.ps1'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Canonical bridge program missing.' }
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$target = Join-Path $InstallRoot 'mobile-proxy-usb-bridge.ps1'
Copy-Item -LiteralPath $source -Destination $target -Force

$owner = "$env:USERDOMAIN\$env:USERNAME"
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$target`" -BusId $busId -HardwareId $HardwareId -Distro $Distro"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $owner
$principal = New-ScheduledTaskPrincipal -UserId $owner -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Attaches only the approved Mobile Proxy Android USB device to WSL after owner logon.'
Register-ScheduledTask -TaskName 'MobileProxyUsbBridge' -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName 'MobileProxyUsbBridge'

Write-Output 'mobile_proxy_usb_bridge_installed=true'
Write-Output 'task_trigger=owner_logon'
Write-Output 'scope=single_preapproved_usb_bus'
