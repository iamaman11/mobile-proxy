# Server-side proxy termination experiment

## Status

Promoted to the production default after physical A/B acceptance. Direct reverse-tunnel forwarding
to the phone protocol engine remains an explicit rollback mode.

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
`server-termination` production mode in a `finally` block. The switch retries bounded transient SSH/IAP failures
and verifies that TCP/443, all public proxy listeners and the exact configuration bytes are active. Credentials
are read only from `MOBILE_PROXY_RELAY_USER` and `MOBILE_PROXY_RELAY_PASSWORD`; they are never
written into the report or child-process command lines. Curl receives its authentication config
through standard input.

The physical acceptance run passed all four proxy surfaces with five concurrent connections each.
Server-side IP rotation changed the address in 14 seconds and returned healthy, publicly serving,
fresh TLS transport state. The reverse-tunnel mode remains available for exact rollback and future
comparative testing.
