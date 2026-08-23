# Server-side proxy termination experiment

## Status

Promoted selectively as the `optimized-hybrid` production default after physical A/B acceptance.
Mixed `1080` and SOCKS `1081` retain phone termination; HTTP/CONNECT `3128` uses VM termination.
Both fully direct and fully VM-terminated paths remain explicit comparison/rollback modes.

## Candidate topology

The VM sing-box owns public HTTP, CONNECT and SOCKS parsing on isolated loopback ports `12080`,
`12081` and `12128`. Its authenticated SOCKS outbound enters the existing reverse-tunnel SOCKS
listener on `14081`. For `first_party_android_egress`, that protocol-specific tunnel route targets
the Android cellular egress listener on `127.0.0.1:18080`, bypassing phone sing-box for the
candidate path.

NGINX public ports are switched atomically by `scripts/switch_vm_proxy_transport.py`. The new
`server-termination` mode requires both the VM sing-box and reverse-tunnel services. Any failed
NGINX validation, service check or exact byte comparison restores the prior configuration.

## Acceptance

`scripts/compare_proxy_topologies.py` compares the protected proxy surfaces with five concurrent
connections by default, waits for NGINX workers to settle before measuring, and always restores
`optimized-hybrid` production mode in a `finally` block. The switch retries bounded transient SSH/IAP failures
and verifies that TCP/443, all public proxy listeners and the exact configuration bytes are active. Credentials
are read only from `MOBILE_PROXY_RELAY_USER` and `MOBILE_PROXY_RELAY_PASSWORD`; they are never
written into the report or child-process command lines. Curl receives its authentication config
through standard input.

Repeated physical runs showed VM HTTP/CONNECT termination was consistently stronger on `3128`,
while the VM mixed inbound intermittently rejected SOCKS method negotiation on `1080`. Production
therefore uses only the accepted per-surface mappings instead of promoting the full candidate.
The TLS fallback maintains eight authenticated idle streams for each active phone session.
Five-way bursts reuse these established cellular connections instead of creating simultaneous TCP
and TLS handshakes. Activated streams are replenished immediately, while bounded on-demand streams
remain available for overflow and rolling upgrades.
Server-side IP rotation changed the address in 14 seconds and returned healthy, publicly serving,
fresh TLS transport state. Both complete modes remain available for exact rollback and comparison.
