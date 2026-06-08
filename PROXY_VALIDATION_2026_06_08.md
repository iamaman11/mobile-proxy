# Proxy Validation 2026-06-08

Workspace: `/home/bose/projects/mobile-proxy`
Relay: `34.118.88.54`
Phone runtime: `first_party_reverse_tunnel`

## Scope

Validated public proxy quality, privacy, and performance for:

- HTTP proxy: `34.118.88.54:3128`
- SOCKS5 proxy: `34.118.88.54:1081`
- mixed proxy as HTTP: `34.118.88.54:1080`
- mixed proxy as SOCKS5: `34.118.88.54:1080`

Validated both plain HTTP target traffic and HTTPS target traffic.

Local result artifacts:

- `target/proxy-quality-quick-20260608.jsonl`
- `target/proxy-privacy-headers-20260608.jsonl`
- `target/proxy-all-soak-20260608.jsonl`
- `target/proxy-parallel-20260608.jsonl`

## Live Health

- `operator-cli verify-device --required-tunnel-owner first_party_reverse_tunnel` passed.
- VM services were active: `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, `mobile-reverse-tunnel-server`, `nginx`.
- Public listeners were present on `1080`, `1081`, and `3128`.
- Internal reverse-tunnel listeners were present on `14080`, `14081`, and `14128`.

## Quality

Quick matrix:

- `3128` HTTP target: `10/10`
- `3128` HTTPS target: `10/10`
- `1081` SOCKS5 HTTP target: `10/10`
- `1081` SOCKS5 HTTPS target: `10/10`
- `1080` mixed-as-HTTP HTTP target: `10/10`
- `1080` mixed-as-HTTP HTTPS target: `10/10`
- `1080` mixed-as-SOCKS HTTP target: `10/10`
- `1080` mixed-as-SOCKS HTTPS target: `10/10`

All-proxy soak:

- `800/800` total successful requests.
- All successful requests returned the same carrier IP: `178.168.187.126`.
- No VM IP or WSL/direct IP was returned by the proxy path.

Authorization:

- `3128` without auth: closed.
- `3128` with wrong auth: closed.
- `1081` without auth: closed.
- `1081` with wrong auth: closed.
- `1080` HTTP mode without auth: closed.
- `1080` HTTP mode with wrong auth: closed.
- `1080` SOCKS mode without auth: closed.
- `1080` SOCKS mode with wrong auth: closed.

## Privacy

Direct WSL public IP during validation: `104.28.193.182`.

Proxy target-observed IP:

- `httpbin.org/ip` over all proxy modes returned only the phone carrier IP: `178.168.187.126`.
- The VM public IP `34.118.88.54` was not exposed as the target-observed client IP.
- The WSL/direct public IP was not exposed as the target-observed client IP.

Plain HTTP header echo via `httpbingo.org` showed `X-Forwarded-For` values containing the phone carrier IP and the echo service's own CDN hop. It did not expose the VM IP or WSL/direct IP. For privacy-sensitive traffic, HTTPS target traffic or SOCKS5 should be preferred.

Important remaining privacy gap:

- Public proxy ingress is raw HTTP/SOCKS TCP, not TLS-wrapped.
- Proxy credentials are protected from target sites, but the client-to-VM proxy authentication exchange is not encrypted by the proxy protocol itself.
- For strict 10/10 privacy on untrusted client networks, add a TLS-protected proxy ingress such as HTTPS proxy over TLS with a pinned certificate, or require a separate encrypted client-to-VM tunnel.

## Performance

All-proxy soak, 100 requests per endpoint/protocol combination:

| Proxy path | Target | Success | Avg total | P95 total | Max total |
|---|---:|---:|---:|---:|---:|
| `3128` HTTP proxy | HTTP | `100/100` | `0.376s` | `0.481s` | `0.780s` |
| `3128` HTTP proxy | HTTPS | `100/100` | `0.547s` | `0.690s` | `0.801s` |
| `1080` mixed as HTTP | HTTP | `100/100` | `0.403s` | `0.503s` | `1.531s` |
| `1080` mixed as HTTP | HTTPS | `100/100` | `0.585s` | `0.818s` | `2.834s` |
| `1080` mixed as SOCKS5 | HTTP | `100/100` | `0.813s` | `0.927s` | `1.024s` |
| `1080` mixed as SOCKS5 | HTTPS | `100/100` | `1.020s` | `1.225s` | `1.890s` |
| `1081` SOCKS5 | HTTP | `100/100` | `0.815s` | `0.999s` | `1.851s` |
| `1081` SOCKS5 | HTTPS | `100/100` | `1.034s` | `1.306s` | `1.962s` |

Parallel HTTPS smoke, 30 concurrent requests per path:

- `3128` HTTP proxy: `30/30`, avg `0.826s`, max `1.107s`.
- `1080` mixed as HTTP: `30/30`, avg `1.018s`, max `1.962s`.
- `1080` mixed as SOCKS5: `30/30`, avg `1.384s`, max `1.812s`.
- `1081` SOCKS5: `30/30`, avg `1.410s`, max `2.300s`.

## Verdict

Proxy serving quality and performance are strong for current live traffic:

- all tested proxy modes work for HTTP and HTTPS targets;
- all tested modes return the phone carrier IP;
- all tested modes require authentication;
- short all-proxy soak and parallel load smoke passed without failures.

The remaining non-10/10 privacy issue is client-to-VM proxy ingress encryption. Target-side privacy is good; ingress credential confidentiality is not yet strict-production-grade on untrusted networks.
