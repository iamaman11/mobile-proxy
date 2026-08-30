# Pre-Device Readiness Audit

> **STATUS: HISTORICAL / NON-NORMATIVE AUDIT**
>
> This document records an earlier pre-device hardening audit and the risks it found. Some implementation details below refer to the retired workstation/GCP-era acceptance tooling. They are retained as historical evidence only and **must not be used as the current acceptance or production runbook**.
>
> Current normative sources are `docs/PRODUCTION_BASELINE_PLAN.md`, `docs/PRE_DEVICE_PREPARATION_CHECKLIST.md`, `docs/physical-phone-acceptance-runbook.md`, `docs/operations/phone-gitops-runtime.md` and the protected operations/governance contracts. Google/GCP is not a current acceptance or production fallback.

Scope at the time of the audit: everything then considered provable or executable before a physical phone was attached.

## Historical audit result

The prior software candidate passed its source and process tests, but a second operator-level audit found physical-gate gaps that could have produced false-positive or non-executable evidence. The audit closed or identified controls for those gaps before a later immutable candidate was accepted.

## Historical findings and closures

1. **Local SHA did not prove deployed identity.**
   - Exact phone-file and VM-file comparison against immutable package roots was introduced.
   - Device release metadata was required to contain candidate SHA and clean-tree evidence.
   - Tunnel-owner and Android VPN-owner verification was made explicit.

2. **Mixed port `1080` was incompletely evidenced.**
   - Software and physical acceptance were expanded to cover SOCKS5, HTTP and CONNECT on mixed `1080`, plus `1081` and `3128` paths.

3. **Public proxy authentication was absent from the physical runner.**
   - Proxy credentials became mandatory protected inputs and were kept out of report payloads.

4. **WireGuard rollback was not an executable reversible procedure.**
   - Bounded reversible server-side switching and configuration verification were introduced in the then-current tooling.
   - The current normative topology no longer authorizes the old GCP/workstation implementation of that mechanism.

5. **Stock WireGuard ownership could false-pass.**
   - Physical verification was strengthened to require the stock WireGuard Android package to own the active VPN during rollback and no Android VPN during native reverse operation.

6. **Return to the original phone release could rebuild or fail to restart.**
   - Immutable release reactivation and exact package-byte verification were introduced as requirements.

7. **Stage health did not prove the phone was serving.**
   - Physical stages were strengthened to require exact node identity, serving state, proxy/cellular readiness, durable availability/heartbeat and exact transport state.

8. **Reports could be accepted independently.**
   - One coherent report-set/identity tuple became a requirement instead of accepting unrelated stage reports independently.

## Historical software-evidence conclusion

The audit concluded that a software candidate must be immutable and that source/process evidence must be complete before physical execution. That principle remains current.

The concrete workstation/GCP commands that existed around this audit are no longer authoritative. Current server acceptance is the GitHub-hosted, typed, durable item-19 Vultr path, and current phone execution is the private `android-production` GitHub Actions boundary.

## Still-relevant physical facts

Facts that still intrinsically require real hardware/network include:

- real root/ADB behavior on the registered phone;
- real cellular routing and public egress;
- real phone/service reboot recovery;
- real QUIC failure while pinned TLS/TCP remains reachable;
- real return to QUIC;
- real stock WireGuard rollback/handshake;
- real authenticated public proxy traversal;
- exact phone/server identity throughout the physical sequence.

For the current required gates and execution sequence, use the normative sources named at the top of this document.
