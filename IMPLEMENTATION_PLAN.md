# Mobile Proxy Implementation Plan

The sole active repository roadmap is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

The normative final acceptance matrix is `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`. Public Issue #228 carries detailed backlog context. The newest authoritative checkpoint in public Issue #179 decides the exact next bounded action and overrides stale roadmap prose.

## Authority

The accepted v2 split is:

```text
PRODUCT
  iamaman11/mobile-proxy
  -> application/runtime source
  -> shared product/domain architecture
  -> Quality
  -> product build + signing verification
  -> annotated product tag
  -> immutable Product Release

DEPLOYMENT CONTROLLER
  iamaman11/mobile-proxy-production
  -> /deploy ingress on Controller Issue #1
  -> deployment State Machine / Transaction Kernel
  -> target admission + serialization + observation/adapters
  -> durable mutation intent
  -> exactly-once destructive dispatch
  -> postcondition / recovery / quarantine
  -> canonical runtime execution classification
```

Both repositories are public. Repository visibility is not the confidentiality boundary. Secrets, target bindings, raw target/device identifiers, credentials, private keys, sensitive rendered configuration and unsafe raw runtime/ADB logs remain private.

Normative authority contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Issue #179 is the single current engineering/migration/execution cursor. Issue #228 is backlog only. Deployment Controller Issue #1 is runtime command/ledger surface. This file never grants `/deploy`, phone/ADB access, provider/VM mutation, signing authority, tag authority or Release mutation.

## Engineering doctrine

The project targets a small, understandable industrial system.

- No code for code.
- No verification of verification.
- Prefer deletion and consolidation over new abstraction layers.
- One owner per state/decision.
- Keep normal flow understandable as `state -> guard -> operation -> effect -> independent observation -> resulting state`.
- Do not preserve disposable bootstrap phone state through complicated compatibility machinery unless continuity becomes an explicit production requirement.
- No new framework is justified merely to reconcile old PRODUCT/controller duplication.

## Durable A-H path

### Gate A — Deployment Controller health

Required controller policies must execute on real runners against the exact current controller revision and finish terminal green. Tree-equivalence alone is insufficient.

### Gate B — source ownership / authority convergence

Remove active duplicate deployment-control ownership from PRODUCT. Keep PRODUCT/shared-domain/build/release code in `mobile-proxy`; keep ingress, target mutation State Machine, durable intent, exactly-once dispatch, recovery/quarantine and canonical runtime execution truth in `mobile-proxy-production`.

Do not create a third shared controller framework. Historical public controller code remains in Git history rather than as a second maintained implementation.

### Gate C — Android secret-state and backup/D2D hardening

- eliminate plaintext persistent WireGuard/private tunnel configuration;
- use the existing AndroidKeyStore/AES-GCM pattern;
- explicitly exclude secret-bearing state from backup/device transfer;
- preserve required direct-boot behavior;
- corrupt/missing ciphertext or key material fails closed;
- no plaintext fallback.

### Gate D — Android behavior and framework integration tests

Protect independent production contracts with a small number of strong tests:

- secure state and corruption refusal;
- boot restoration / desired-state behavior;
- tunnel lifecycle/backend failure;
- cellular-egress authentication and network refusal;
- local-control authentication and bounded retry/timeout behavior;
- one instrumentation/emulator smoke path for actual Android framework/Keystore/service integration.

### Gate E — supply-chain provenance + Product Release prerequisite hardening

- bind the vendored WireGuard AAR to authoritative upstream identity/version/license/digest;
- do not load Android signing secret values merely to prove prerequisite configuration;
- require exact same-SHA successful Quality and Product Release prerequisite proof before product tag creation.

### Gate F — new immutable Product Release

Create the next semantic Product Release only from the hardened exact PRODUCT revision. Do not rewrite historical `v0.1.4`. Require exact annotated tag -> exact source -> exact signed artifacts -> manifest/provenance/digests -> immutable GitHub Release.

### Gate G — exactly one admitted deployment

Only when #179 explicitly authorizes it, submit exactly one semantic:

```text
/deploy <target> <new-release>
```

The Deployment Controller must bind exact immutable Product Release + exact controller revision, serialize the target, persist intent before destructive dispatch, perform at most one effect, independently observe postconditions and fail closed into read-only recovery after an ambiguous physical boundary.

No old failed GitHub run is manually rerun to perform a deployment. Re-entry comes only from the canonical controller ledger.

### Gate H — real-world acceptance

Prove the deployed immutable release on the registered phone through reverse tunnel, relay/provider, external client, cellular egress/IP rotation, reboot/fallback/recovery and reliability/soak criteria in `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`.

Historical phone experiments prove parts of the path but never substitute for Gate H on the final immutable Product Release.

## Runtime identity

```text
product_release
  = exact semantic tag
  + exact PRODUCT source SHA
  + immutable Product Release asset/provenance set

runtime_deployment_identity
  = product_release
  + exact admitted controller revision
```

The PRODUCT and controller revisions belong to different repositories and are intentionally not required to be equal.

## Deployment-controller invariants PRODUCT work must not break

- semantic request identity is independent of GitHub comment/run/attempt provenance;
- public GitHub Deployment is projection only;
- durable mutation intent precedes destructive dispatch;
- one durable intent admits at most one destructive dispatch;
- ambiguous post-dispatch state never causes blind destructive retry;
- UNKNOWN continuation is read-only observation/reconciliation;
- `RECOVERED != ACCEPTED`;
- target serialization is controller-owned;
- controller durable terminal classification is runtime truth;
- sensitive target/secret data remains private even though controller source/policy is public.

## Quality

For docs/policy-sized work:

```bash
scripts/quality-gate.sh fast
```

For code/release work:

```bash
scripts/quality-gate.sh
```

GitHub `Quality Gate` is aggregate PRODUCT software/policy evidence. It does not manufacture current target state or authorize deployment.

## Definition of done

Full production 10/10 requires all three evidence domains:

1. PRODUCT security, behavior, Quality, release-gate and dependency provenance are proven.
2. Deployment Controller exactly-once mutation, target observation, recovery/quarantine and terminal evidence are proven.
3. The separately authorized real target acceptance/recovery/soak sequence passes with no unresolved P0/P1 defect.

The newest #179 checkpoint remains the only authority for the exact next bounded step.
