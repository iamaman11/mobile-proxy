# Transport-neutral runtime domain boundary

## Decision

`crates/runtime-domain` owns only deterministic lifecycle state, events, actions and transitions. It does not know which tunnel adapter is selected.

The domain vocabulary is:

```text
BOOTING
WAITING_TUNNEL
WAITING_CELLULAR
STARTING_PROXY
HEALTHY
RECOVERING
QUARANTINED
```

QUIC, certificate-pinned TLS/TCP and WireGuard compatibility remain adapter capabilities. They must not appear in runtime-domain source or dependencies.

## Compatibility adapter

The existing public readiness value `waiting_wireguard` remains protected. `runtime-supervisor` translates it to `WaitingTunnel` on ingress and translates `WaitingTunnel` back to `waiting_wireguard` when projecting the legacy surface. This isolates historical vocabulary without silently changing operator or control-plane contracts.

Unknown public readiness values fail closed to the neutral `Recovering` state. They are never copied into a domain enum or emitted as an unbounded label.

## Production composition

`runtime-supervisor` observes every authenticated host health record and maintains the neutral lifecycle projection. State changes are logged with bounded enum values and the compatible readiness projection. The projection is observational in this slice: existing recovery commands, readiness decisions, proxy listeners and transport selection are unchanged.

## Enforcement

`scripts/check_architecture_boundaries.py` rejects:

- dependencies other than the explicitly allowed pure dependency set;
- infrastructure frameworks and runtime libraries in domain source;
- filesystem, network, process and environment access;
- Android or WireGuard-specific vocabulary;
- a dependency back to transitional `proxy-core`.

The validator and its regression tests run in the permanent `Rust Quality` workflow and the complete local quality gate.

## Next extraction

The next Phase 1 slice should introduce typed foundation identifiers and deadlines, then move application orchestration behind ports without changing the protected proxy or operator surface.
