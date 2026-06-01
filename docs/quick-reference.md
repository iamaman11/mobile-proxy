# Quick Reference

## Local Reconstruction

- project root: `\\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy`
- build Rust workspace: `cargo build`
- run Rust tests: `cargo test`
- start local dev stack: `.\scripts\start-local-stack.ps1 -Token replace_me`
- smoke-test local dev stack: `.\scripts\test-local-stack.ps1 -Token replace_me`

## Public Relay

- relay IP: `34.118.26.142`
- mixed: `34.118.26.142:1080`
- SOCKS5: `34.118.26.142:1081`
- HTTP/HTTPS CONNECT: `34.118.26.142:3128`

Credentials are not committed. Set runtime credentials in environment variables:

- `MOBILE_PROXY_RELAY_USER`
- `MOBILE_PROXY_RELAY_PASSWORD`

Quick public proxy smoke test:

```powershell
.\scripts\test-public-proxy.ps1
```

## Required Secrets

```powershell
$env:MOBILE_PROXY_ADMIN_TOKEN='replace_admin_token'
$env:MOBILE_PROXY_DEVICE_TOKEN='replace_device_token'
$env:MOBILE_PROXY_RELAY_USER='replace_relay_user'
$env:MOBILE_PROXY_RELAY_PASSWORD='replace_relay_password'
```

## Device Runtime Deployment

Phone prerequisites:

- `adb shell su 0 sh -c "id"` returns `uid=0`
- `adb shell pm list packages com.wireguard.android` returns installed package
- tunnel `WiGandroid` exists in WireGuard app and can be started

Install a versioned release:

```powershell
.\scripts\device\install-device.ps1 `
  -ManifestPath .\deploy\manifests\devices\example-device.json `
  -ReleaseId 2026.06.01
```

Verify device health and proxy readiness:

```powershell
.\scripts\device\verify-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
```

Roll back to previous or explicit release:

```powershell
.\scripts\device\rollback-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
.\scripts\device\rollback-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json -ReleaseId 2026.05.31
```

## Rotate IP

If local API access is not configured yet:

```powershell
& "C:\Users\Bose\AppData\Local\Android\Sdk\platform-tools\adb.exe" forward tcp:18088 tcp:8088
```

Manual rotation:

```powershell
$h=@{Authorization="Bearer $env:MOBILE_PROXY_ADMIN_TOKEN"};$b='{"strategy":"airplane_bounce","require_public_ip_change":true,"reason":"manual-rotate"}';$id=(Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:18088/v1/ip/rotate' -Headers $h -ContentType 'application/json' -Body $b).job_id;do{$s=Invoke-RestMethod -Uri "http://127.0.0.1:18088/v1/jobs/$id" -Headers $h;$x=Invoke-RestMethod -Uri 'http://127.0.0.1:18088/v1/health' -Headers $h;"{0} job={1} state={2} serving={3} old={4} new={5}" -f (Get-Date -Format HH:mm:ss),$s.status,$x.readiness_state,$x.serving,$s.old_public_ip,$s.new_public_ip;Start-Sleep 2}while($s.status -eq 'running');$s|ConvertTo-Json -Depth 5
```
