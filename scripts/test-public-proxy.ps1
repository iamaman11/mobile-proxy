param(
    [string]$RelayHost = "34.118.26.142",
    [string]$Username = "relay4855cb91",
    [string]$Password = "4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9",
    [string]$HttpTestUrl = "http://httpbin.org/ip",
    [string]$HttpsTestUrl = "https://httpbin.org/ip",
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

function Invoke-ProxyProbe {
    param(
        [string]$Name,
        [string]$Proxy,
        [string]$Url
    )

    Write-Output "== $Name =="
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $body = & curl.exe --fail --silent --show-error --max-time $TimeoutSeconds `
            --proxy $Proxy `
            --proxy-user "${Username}:${Password}" `
            $Url
        if ($LASTEXITCODE -eq 0) {
            $body
            return
        }
        if ($attempt -lt 5) {
            Start-Sleep -Seconds 2
        }
    }
    throw "curl failed for $Name after 5 attempts"
}

Invoke-ProxyProbe -Name "socks5h:1081 -> http" -Proxy "socks5h://${RelayHost}:1081" -Url $HttpTestUrl
Invoke-ProxyProbe -Name "mixed:1080 -> http" -Proxy "http://${RelayHost}:1080" -Url $HttpTestUrl
Invoke-ProxyProbe -Name "mixed:1080 -> https" -Proxy "http://${RelayHost}:1080" -Url $HttpsTestUrl
Invoke-ProxyProbe -Name "http-connect:3128 -> http" -Proxy "http://${RelayHost}:3128" -Url $HttpTestUrl
Invoke-ProxyProbe -Name "http-connect:3128 -> https" -Proxy "http://${RelayHost}:3128" -Url $HttpsTestUrl

Write-Output "public proxy smoke test passed"
