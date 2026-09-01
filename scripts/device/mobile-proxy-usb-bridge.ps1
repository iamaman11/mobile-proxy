<#
.SYNOPSIS
    Maintains the one approved Android USB transport from Windows to WSL.

.DESCRIPTION
    Windows owns the physical USB controller, while the private GitHub Actions runner lives in
    WSL. This program attaches only one pre-approved physical USB bus to WSL and keeps usbipd
    auto-attach active for reconnects. It never invokes ADB, installs an APK, or changes a phone.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\d+-\d+$')]
    [string]$BusId,

    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}$')]
    [string]$HardwareId,

    [string]$Distro = 'Ubuntu',

    [string]$LogPath = 'C:\ProgramData\MobileProxy\usb-bridge\bridge.log'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-BridgeLog {
    param([Parameter(Mandatory)][string]$Message)

    $directory = Split-Path -Parent $LogPath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    Add-Content -LiteralPath $LogPath -Value ('{0:o} {1}' -f (Get-Date), $Message)
}

function Get-ApprovedUsbState {
    $lines = @(& usbipd.exe list 2>$null | Select-Object -Skip 1)
    $busPattern = [regex]::Escape($BusId)
    $hardwarePattern = [regex]::Escape($HardwareId)
    $matches = @($lines | Where-Object { $_ -match "^\s*$busPattern\s+$hardwarePattern\s+" })
    if ($matches.Count -ne 1) { return $null }
    $line = [string]$matches[0]
    if ($line -match '\bAttached\b') { return 'Attached' }
    if ($line -match '\bShared\b') { return 'Shared' }
    if ($line -match '\bNot shared\b') { return 'NotShared' }
    return 'Unknown'
}

try {
    if (-not (Get-Command usbipd.exe -ErrorAction SilentlyContinue)) { throw 'usbipd unavailable' }
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'wsl unavailable' }

    # LocalSystem cannot access a per-user WSL distribution. This task is intentionally owned by
    # the WSL user and starts only after that user logs in.
    & wsl.exe -d $Distro -- bash -lc 'systemctl is-active mobile-proxy-phone-runner.service >/dev/null'
    if ($LASTEXITCODE -ne 0) { throw 'private WSL runner unavailable' }

    $deadline = (Get-Date).AddMinutes(2)
    do {
        $state = Get-ApprovedUsbState
        if ($state -eq 'NotShared') {
            & usbipd.exe bind --busid $BusId | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'approved USB bind failed' }
            Start-Sleep -Seconds 2
            $state = Get-ApprovedUsbState
        }
        if ($state -eq 'Shared') { break }
        if ($state -eq 'Attached') {
            # Take ownership of the existing attachment so this task, rather than an interactive
            # usbipd client, retains reconnect handling for the rest of the Windows session.
            & usbipd.exe detach --busid $BusId | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'approved USB detach failed' }
            Start-Sleep -Seconds 2
            $state = Get-ApprovedUsbState
            if ($state -eq 'Shared') { break }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($state -ne 'Shared') { throw 'approved USB unavailable' }
    Write-BridgeLog 'approved_usb_auto_attach_started'
    $parts = $HardwareId.Split(':')
    $permissionsJob = Start-Job -ArgumentList $Distro, $parts[0], $parts[1] -ScriptBlock {
        param($TargetDistro, $VendorId, $ProductId)

        # usbipd can attach after WSL's initial udev event window. Repair only this VID:PID's
        # Linux node permissions and the local runner ADB daemon; this never sends a device shell
        # command or changes phone state.
        while ($true) {
            Start-Sleep -Seconds 5
            $state = @(& wsl.exe -d $TargetDistro -- bash -lc 'sudo -u mobileproxyphone -H adb get-state 2>/dev/null || true')
            if ($state -notcontains 'device') {
                $repair = "sudo -n udevadm control --reload-rules; sudo -n udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=$VendorId --attr-match=idProduct=$ProductId; sudo -n udevadm settle; sudo -n -u mobileproxyphone -H /usr/bin/adb kill-server || true"
                & wsl.exe -d $TargetDistro -- bash -lc $repair | Out-Null
            }
            Start-Sleep -Seconds 25
        }
    }
    & usbipd.exe attach --wsl $Distro --busid $BusId --auto-attach --unplugged
    if ($LASTEXITCODE -ne 0) { throw 'usbipd auto-attach failed' }
    throw 'usbipd auto-attach stopped'
}
catch {
    # No identifiers, ADB output, secrets, or arbitrary exception text in the persistent log.
    Write-BridgeLog 'approved_usb_bridge_failed'
    exit 1
}
