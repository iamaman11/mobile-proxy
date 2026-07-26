# Native Runtime and BLAKE3 Pre-Device Audit Closeout

Status: source-controlled closeout pending final immutable workflow evidence  
Scope: everything that can be corrected and proven without a physical phone

## Trigger

The earlier software candidate treated Android VPN ownership too broadly and claimed pre-device completeness before verifying repository-wide tunnel defaults, operator behavior and non-Rust digest tooling. That claim was withdrawn and physical issue #64 was blocked.

## Correct production architecture

The normal phone runtime is rooted and native:

- Magisk/service.d boot hook;
- `runtime-supervisor`;
- `host-daemon`;
- loopback `sing-box`;
- QUIC-first reverse tunnel;
- certificate-pinned TLS/TCP reserve;
- no active Android VPN;
- no `tun0` dependency.

The supported tunnel-owner values are:

- `first_party_reverse_tunnel` — default and primary;
- `stock_wireguard_bridge` — explicit stock WireGuard rollback compatibility;
- `first_party_vpn_service` — app-owned Android `VpnService` compatibility mode, currently disabled.

`first_party_vpn_service` is not the primary production transport. Physical validation on July 26, 2026 showed that the Android `VpnService` path did not expose a routable `10.66.66.2` listener for the rooted proxy runtime on a real Samsung device, so the owner is now fail-closed until the compatibility topology is redesigned and revalidated.

## Corrected findings

### Tunnel ownership and defaults

- package, install-stack, install-release and verify default to native reverse tunnel;
- missing, unknown or contradictory owner configuration fails closed;
- owner and `wireguard.enabled` must agree;
- normal native reverse-tunnel installation never installs or requires the Android APK;
- normal verification requires no active Android VPN;
- stock rollback verifies the actual `com.wireguard.android` owner UID;
- native startup stops incompatible stock or app-owned Android VPN state before serving.

### Device deployment safety

- release IDs and root paths are strictly bounded before root-shell use;
- package creation requires a clean Git worktree;
- package metadata records the full exact SHA;
- JSON templates use proper JSON serialization instead of raw replacement;
- unresolved placeholders and malformed/custom contradictory configs fail closed;
- phone files are compared byte-for-byte after installation;
- rollback stops the existing watchdog/processes and performs a full runtime restart;
- returning from WireGuard reactivates the exact already-installed native release without rebuilding.

### Secrets and diagnostics

- host API bearer tokens are sent through the HTTP client, not process arguments;
- proxy credentials use the HTTP client's authentication surface or curl stdin configuration, not credential-bearing URLs/argv;
- proxy bypass variables are disabled during physical proxy checks;
- curl shim logs result only, not probe URL or credentials;
- temporary local scripts are permission-restricted and removed;
- bounded failures do not echo token or password values.

### BLAKE3 policy

- typed internal BLAKE3 remains the only project-owned content/fingerprint digest contract;
- release roots are verified through sorted `integrity-manifest.json` entries with typed `b3:` values and exact sizes;
- active phone and VM files are compared by exact bytes after BLAKE3 package verification;
- switchable VM proxy configuration is compared by exact bytes;
- newly introduced internal SHA-256 contracts were removed;
- the permanent gate scans production Rust, Python, shell and Kotlin for direct first-party SHA-256 and untyped BLAKE3;
- direct Cargo `blake3` ownership is confined to the typed foundation crate;
- external SHA-256 contracts such as TLS, Cargo registry and GitHub artifact digests are preserved.

### Acceptance and supply chain

The mandatory software workflows now include:

- architecture/native-runtime/digest policies;
- Python regressions;
- rustfmt;
- strict Clippy;
- full workspace tests;
- process liveness/readiness;
- SQLite migration, backup and clean restore;
- forced QUIC failure, pinned TLS/TCP reserve and QUIC recovery;
- all protected proxy protocols;
- RustSec advisory audit;
- cargo-deny advisories, licenses, bans and sources;
- Android unit tests, lint and debug assembly;
- immutable evidence v2.

Evidence v2 explicitly records:

- native reverse-tunnel primary;
- no Android VPN requirement for primary runtime;
- stock WireGuard rollback;
- app-owned WireGuard compatibility path explicitly disabled pending redesign and new physical validation;
- `software_10_of_10_ready=true`;
- `physical_phone_acceptance_required=true`;
- `baseline_complete=false`.

The physical runner rejects older evidence versions and any evidence that weakens these statements.

## Permanent enforcement

The following controls make the corrections non-optional:

- `scripts/check_native_runtime_policy.py`;
- `scripts/check_digest_policy.py`;
- `scripts/check_architecture_boundaries.py`;
- unit tests for tunnel defaults and owner/flag agreement;
- exact deployment and report-set validators;
- immutable release-candidate workflow.

## Honest completion boundary

This closeout may authorize a new software candidate only after both quality workflows succeed on the same unchanged SHA and produce evidence v2.

It does not claim final 10/10. Final acceptance additionally requires:

- clean real-phone install;
- real QUIC, reboot, pinned TLS/TCP fallback and QUIC return;
- explicit stock WireGuard rollback and exact native restoration;
- all authenticated proxy surfaces;
- repeated recovery thresholds;
- operator-specific rotation matrix;
- 24-hour soak;
- no unresolved P0/P1 defect.

Those requirements are defined in `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` and executed beginning with `docs/physical-phone-acceptance-runbook.md`.
