param(
    [string]$ControlPlaneUrl = "http://127.0.0.1:8080",
    [string]$ApiToken = ""
)

$ErrorActionPreference = "Stop"

if (-not $ApiToken) {
    $ApiToken = $env:MOBILE_PROXY_DEVICE_TOKEN
}

if (-not $ApiToken) {
    throw "Missing API token. Set -ApiToken or MOBILE_PROXY_DEVICE_TOKEN."
}

$headers = @{ Authorization = "Bearer $ApiToken" }

$devices = Invoke-RestMethod -Uri "$ControlPlaneUrl/api/v1/devices" -Headers $headers
$ready = Invoke-RestMethod -Uri "$ControlPlaneUrl/api/v1/devices/ready" -Headers $headers

$rows = @($devices | ForEach-Object {
    [pscustomobject]@{
        node_id = $_.node_id
        node_name = $_.node_name
        availability = $_.availability
        readiness_state = $_.readiness_state
        serving = $_.serving
        proxy_status = $_.proxy_status
        last_public_ip = $_.last_public_ip
        heartbeat_at = $_.heartbeat_at
        last_error = $_.last_proxy_error
    }
})

$rows | Format-Table -AutoSize
Write-Output ""
Write-Output ("total_devices={0} ready_devices={1}" -f $rows.Count, @($ready).Count)
