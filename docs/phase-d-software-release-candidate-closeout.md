# Phase D Software-Complete Release Candidate Closeout

Status: delivery item 14 implementation candidate  
Issue: #62  
Scope: all source-controlled and process-testable production-baseline acceptance

## Decision

The software baseline is accepted only by the dedicated `Software Release Candidate` workflow on one immutable candidate SHA.

For pull requests, the candidate SHA is the exact pull-request head commit checked out explicitly by the workflow. For `main` pushes and manual dispatch, it is the exact workflow SHA. The workflow fails before testing if the checked-out commit differs from `CANDIDATE_SHA` or the checkout is dirty.

The workflow-generated `release-candidate-evidence.json` is the authoritative candidate identity. A branch name, mutable tag, local working tree or successful run from another SHA is not acceptable evidence.

## Complete software acceptance

The immutable workflow runs:

1. checkout/SHA and clean-tree verification;
2. architecture and digest-policy enforcement;
3. all Python regression tests, including evidence and physical-runner fail-closed checks;
4. rustfmt verification;
5. strict workspace Clippy with warnings denied;
6. real process liveness/readiness acceptance;
7. SQLite backup, verification and clean-environment restore acceptance;
8. state migration and rollback compatibility acceptance;
9. forced QUIC failure, certificate-pinned TLS/TCP reserve, mixed/SOCKS5/HTTP/CONNECT behavior and return-to-QUIC acceptance;
10. the complete Rust workspace test suite;
11. bounded candidate evidence generation and artifact upload.

The evidence contains only fixed acceptance names, repository/workflow identity and the exact candidate SHA. It does not contain credentials, proxy URLs, raw errors, database contents or unbounded labels.

## Software-complete criteria

Delivery item 14 is complete only when:

- both normal `Rust Quality` and `Software Release Candidate` checks succeed for the candidate source;
- the candidate evidence artifact exists and its `candidate_sha` equals the checked-out commit;
- that exact commit is retained as the software-complete candidate used for physical acceptance;
- no unresolved P0/P1 defect affects the production-baseline invariants;
- the physical runbook is executable without source changes;
- no source-controlled or process-testable baseline task remains open.

## Physical gate

`docs/physical-phone-acceptance-runbook.md` and `scripts/run_physical_phone_acceptance.py` define delivery item 15 against the exact evidence SHA. They cover:

- clean startup;
- all three protected proxy ports plus HTTP CONNECT;
- phone/service reboot and durable state rehydration;
- QUIC primary operation;
- forced certificate-pinned TLS/TCP fallback;
- return to QUIC;
- WireGuard rollback availability.

Each stage emits a bounded JSON report bound to the same candidate SHA and never writes tokens.

## Compatibility and non-goals

Protected ports `1080`, `1081` and `3128`, API contracts, SQLite runtime ownership, QUIC primary, certificate-pinned TLS/TCP reserve and WireGuard rollback remain unchanged. No first-party Android tunnel replacement, lease platform, credential broker, protocol migration or future-roadmap platform work is introduced.

## Stop condition

After the immutable candidate workflow succeeds and this closeout is accepted, the only permitted remaining production-baseline gate is delivery item 15: physical-phone acceptance on that exact SHA. Final baseline closeout remains delivery item 16 and cannot be completed before the physical reports pass.
