# Server-side proxy termination experiment

## Status

Implemented as an explicit A/B candidate. The production default remains direct reverse-tunnel
forwarding to the phone protocol engine.

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
connections by default and always restores `reverse-tunnel` mode in a `finally` block. Credentials
are read only from `MOBILE_PROXY_RELAY_USER` and `MOBILE_PROXY_RELAY_PASSWORD`; they are never
written into the report or child-process command lines. Curl receives its authentication config
through standard input.

The candidate must not become the default unless all surfaces pass, throughput and latency do not
regress, Android CPU/RAM decrease, IP rotation remains reliable and exact rollback is proven on the
physical deployment.
