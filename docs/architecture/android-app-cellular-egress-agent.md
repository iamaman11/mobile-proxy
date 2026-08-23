# Android app-owned cellular egress agent

## Status

Implemented as an opt-in phone-local data-plane component. It is not yet selected by
the immutable device release, and therefore cannot make the public ingress serving.

## Why it exists

The rooted `sing-box` process can reach the phone-local SOCKS listener but its outbound
sockets do not acquire Android's cellular `netId`. Binding an interface or manually
reproducing Android firewall marks is not a supported replacement for application UID
network ownership.

`CellularEgressService` is a foreground service running under the application UID. It
listens only on `127.0.0.1`, authenticates SOCKS5 username/password requests, selects a
validated `TRANSPORT_CELLULAR` `Network`, resolves host names through that `Network`,
and invokes `Network.bindSocket` before every outbound TCP connect.

## Control boundary

The receiver accepts three explicit private control commands:

- `SET_EGRESS_CONFIG`: stores port, username and password; the password is encrypted
  by the Android Keystore before persistence.
- `START_CELLULAR_EGRESS`
- `STOP_CELLULAR_EGRESS`

Secrets must be supplied only from the existing secure provisioning path. They must not
be written to release files, command-line history or logs.

For rooted runtime startup, the supervisor writes a one-time JSON configuration into
the application's device-protected private files directory, fixes its ownership and
starts the foreground service under the application UID. The service imports it into
Keystore-backed preferences and deletes the file. This keeps proxy credentials out of
`am` extras and process arguments.

## Required integration gate

Before this component can become the production data plane, the device package must
make the reverse tunnel's `local_proxy_addr` target the app listener and must stop
starting the root-owned `sing-box` listener on that port. The host daemon must report
the app-agent's authenticated readiness, including a successful external DNS/TCP/HTTPS
probe through it. Relay-gate must require that readiness before public ingress is
opened. Until those changes and the physical acceptance tests pass, serving remains
fail-closed.
