# Quick Reference

## Local Reconstruction

- project root: `C:\Users\Bose\temp\mobile`
- build Rust workspace: `cargo build`
- run Rust tests: `cargo test`
- start local dev stack: `.\scripts\start-local-stack.ps1 -Token replace_me`
- smoke-test local dev stack: `.\scripts\test-local-stack.ps1 -Token replace_me`

## Public Relay

- relay IP: `34.118.26.142`
- mixed: `34.118.26.142:1080`
- SOCKS5: `34.118.26.142:1081`
- HTTP/HTTPS CONNECT: `34.118.26.142:3128`

Use current runtime credentials:

- username: `relay4855cb91`
- password: `4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9`

## Proxy Parameters

All public proxy listeners use the same credentials:

- username: `relay4855cb91`
- password: `4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9`

Quick smoke test:

```powershell
.\scripts\test-public-proxy.ps1
```

### SOCKS5

```text
host=34.118.26.142
port=1081
username=relay4855cb91
password=4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9
scheme=socks5
url=socks5h://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:1081
http_test_url=http://httpbin.org/ip
https_test_url=https://httpbin.org/ip
```

### HTTP / HTTPS CONNECT

```text
host=34.118.26.142
port=3128
username=relay4855cb91
password=4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9
scheme=http
url=http://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:3128
http_test_url=http://httpbin.org/ip
https_test_url=https://httpbin.org/ip
```

### Mixed

```text
host=34.118.26.142
port=1080
username=relay4855cb91
password=4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9
scheme=http
url=http://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:1080
http_test_url=http://httpbin.org/ip
https_test_url=https://httpbin.org/ip
```

## Local API

If local API access is not configured yet:

```powershell
& "C:\Users\Bose\AppData\Local\Android\Sdk\platform-tools\adb.exe" forward tcp:18088 tcp:8088
```

## Rotate IP

The active phone runtime uses `airplane_bounce`: airplane mode is enabled, held for 4 seconds, then disabled.

```powershell
$h=@{Authorization='Bearer REPLACE_ADMIN_TOKEN'};$b='{"strategy":"airplane_bounce","require_public_ip_change":true,"reason":"manual-rotate"}';$id=(Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:18088/v1/ip/rotate' -Headers $h -ContentType 'application/json' -Body $b).job_id;do{$s=Invoke-RestMethod -Uri "http://127.0.0.1:18088/v1/jobs/$id" -Headers $h;$x=Invoke-RestMethod -Uri 'http://127.0.0.1:18088/v1/health' -Headers $h;"{0} job={1} state={2} serving={3} old={4} new={5}" -f (Get-Date -Format HH:mm:ss),$s.status,$x.readiness_state,$x.serving,$s.old_public_ip,$s.new_public_ip;Start-Sleep 2}while($s.status -eq 'running');$s|ConvertTo-Json -Depth 5
```
