param(
    [string]$Token = "replace_me"
)

$ErrorActionPreference = "Stop"
$headers = @{ Authorization = "Bearer $Token" }

Write-Output "health"
Invoke-RestMethod -Uri "http://127.0.0.1:8088/v1/health" -Headers $headers | ConvertTo-Json -Depth 5

Write-Output "register-ready"
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/devices/ready" | ConvertTo-Json -Depth 5

Write-Output "rotate"
$job = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8088/v1/ip/rotate" -Headers $headers -ContentType "application/json" -Body '{"strategy":"airplane_bounce","require_public_ip_change":true,"reason":"local-test"}'
Start-Sleep 6
Invoke-RestMethod -Uri ("http://127.0.0.1:8088/v1/jobs/" + $job.job_id) -Headers $headers | ConvertTo-Json -Depth 5
