# Phase D Software-Complete Release Candidate Closeout

Status: delivery item 14 acceptance contract  
Issue: #62  
Scope: all source-controlled and process-testable production-baseline acceptance

## Decision

The software baseline is accepted only by the aggregate `Quality` workflow on one immutable candidate SHA. The required `Quality Gate` remains the single repository merge and software-acceptance gate; a separate duplicate release-candidate workflow is not part of the current Git delivery architecture.

For pull requests, the candidate SHA is the exact pull-request head commit checked out explicitly by the workflow. For `main` pushes and manual dispatch, it is the exact workflow SHA. Code-affecting acceptance runs create `release-candidate-evidence.json` only after architecture/policy, Rust, supply-chain and Android jobs all succeed. Merge-group validation remains merge-queue evidence and does not emit a retained software-candidate artifact.

The workflow-generated `release-candidate-evidence.json` is the authoritative candidate identity. Its writer fails closed if the checked-out commit differs from `CANDIDATE_SHA` or the checkout is dirty. A branch name, mutable tag, local working tree, documentation-only shortcut or successful run from another SHA is not acceptable software-candidate evidence.

The historical standalone `Software Release Candidate` workflow was removed when delivery and quality control were consolidated into Git. This closeout follows the current repository rule that one aggregate `Quality Gate` avoids duplicate test work while still emitting bounded immutable evidence.

## Complete software acceptance

For a code-affecting candidate, the aggregate workflow runs and requires:

1. immutable checkout identity through `CANDIDATE_SHA`;
2. architecture/policy enforcement and all Python regression tests, including candidate-evidence and physical-runner fail-closed checks;
3. locked Rust dependency graph and rustfmt verification;
4. strict workspace Clippy with warnings denied;
5. the complete Rust workspace test suite, including real process liveness/readiness acceptance;
6. SQLite backup, verification, clean-environment restore, state migration and rollback compatibility acceptance;
7. forced QUIC failure, certificate-pinned TLS/TCP reserve, mixed/SOCKS5/HTTP/CONNECT behavior and return-to-QUIC acceptance;
8. RustSec, license, ban and source policy;
9. Android unit tests, lint and debug assembly;
10. bounded release-candidate evidence generation and artifact upload only after all preceding required jobs succeed;
11. the aggregate `Quality Gate`, which fails if candidate evidence was required but not produced successfully.

The evidence contains only fixed acceptance names, repository/workflow identity and the exact candidate SHA. It does not contain credentials, proxy URLs, raw errors, database contents or unbounded labels.

A documentation-only pull request may use the repository's documented lightweight Quality path, but such a run does not create a new software-complete candidate. `workflow_dispatch` has no comparison base and therefore takes the full code gate, allowing the current exact SHA to be requalified when an explicit full rerun is required.

## Software-complete criteria

Delivery item 14 is complete only when:

- `Quality Gate` succeeds on the exact retained candidate SHA with the full code gate;
- the `software-release-candidate-<sha>` evidence artifact exists and its `candidate_sha` equals the checked-out commit;
- that exact commit is retained as the software-complete candidate used for physical acceptance;
- no unresolved P0/P1 defect affects the production-baseline invariants;
- the physical runbook is executable without source changes;
- no source-controlled or process-testable baseline task remains open.

Any later source change invalidates the retained candidate for physical acceptance until the full software gate produces fresh evidence for the later SHA.

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

This acceptance integration does not restore the retired duplicate workflow and does not add a second test suite. It only binds the existing aggregate Quality results to the existing immutable candidate-evidence contract.

## Stop condition

After the aggregate Quality workflow succeeds with full candidate evidence on the retained `main` SHA and this closeout has no earlier software residual, the only permitted remaining production-baseline gate is delivery item 15: physical-phone acceptance on that exact SHA. Final baseline closeout remains delivery item 16 and cannot be completed before the physical reports pass.
