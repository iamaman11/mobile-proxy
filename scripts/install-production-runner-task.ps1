$ErrorActionPreference = 'Stop'

$taskName = 'Mobile Proxy Production Runner'
$wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
$arguments = '-d Ubuntu --exec /home/bose/.local/share/actions-runner/mobile-proxy-production/run-production.sh'

$action = New-ScheduledTaskAction -Execute $wsl -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Trusted GitHub Actions runner for private iamaman11/mobile-proxy production deployments.' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
