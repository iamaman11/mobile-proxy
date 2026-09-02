# Production Baseline Plan

Status: **active canonical implementation roadmap**  
Repository: `iamaman11/mobile-proxy`  
Acceptance matrix: `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`

This file is the **sole canonical implementation roadmap for current development**. The historical label **Production Baseline (Phase 0)** refers to this active baseline, not to a separate authority. `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` is future-only and cannot define current candidate, gate or release state.

## 1. Decision

The near-term objective is a demonstrably reliable production baseline, not speculative platform expansion. Every change must remove a concrete reliability, durability, recovery, security, execution-boundary or release-integrity risk while preserving the protected proxy surface.

The public repository is the sole project/policy/source authority. `iamaman11/mobile-proxy-production` is a private execution satellite for secrets, runner access, thin callers/shims and bounded private evidence only. It must not become a parallel architecture, roadmap, acceptance or release-policy engine.

A green CI result is necessary but not equivalent to global 10/10 acceptance. Architecture/documentation reconciliation is complete when source-controlled contracts/docs/tests are coherent and Quality protects them. Full project 10/10 remains blocked until the same exact immutable candidate also passes the required live provider, Android migration/signing, physical phone, recovery/restart/crash, soak and final-release gates.

Production execution is **fact-first**. The canonical [`control-state-machine-v1.md`](control-state-machine-v1.md) determines what is proven from bounded current evidence; [`operation-state-machine-v1.md`](operation-state-machine-v1.md) determines what exact phase may execute next in one transaction. Workflow conclusion, issue narrative, remembered progress and historical success are not substitutes for those derived states.

For Android physical state, the real registered production phone is the authoritative observation oracle. Hosted `Quality`, unit/integration tests and execution workflows are necessary to prove software/policy coherence and safe observers, but they do not by themselves prove the phone's current filesystem, package, signer, runtime, process, network or functional data-path state.

## 2. Protected compatibility and runtime surface

The baseline preserves:

- mixed proxy on public port `1080`;
- SOCKS5 on `1081`;
- HTTP/CONNECT on `3128`;
- QUIC-first reverse tunnel;
- certificate-pinned TLS/TCP reserve;
- controlled stock-WireGuard compatibility/rollback;
- existing operator CLI/admin API compatibility unless a versioned migration explicitly changes it.

The primary runtime is the rooted/native `first_party_reverse_tunnel`; the Android app is not its primary tunnel owner. The app is a managed production auxiliary component where the selected topology uses `first_party_android_egress` / cellular `Network.bindSocket()` or the app-owned WireGuard compatibility path. A native topology that does not consume an app capability need not install an APK. A topology that does consume it must prove exact package/version/signer-match/install state plus retained signed-artifact digest/provenance for the accepted candidate.

The retired Google/GCP path, manual SSH, raw/manual ADB and ad-hoc provider CLI are not acceptance or production fallbacks.

## 3. Normative release identity

The final Item 20 -> Item 21 chain has exactly one software identity:

```text
candidate_sha
  == control_plane_sha
  == exact protected public main SHA selected for the acceptance window
  == final_accepted_candidate_sha
  == final annotated tag target SHA
  == source SHA of published artifacts
```

Item 20 selects the exact current protected `main` revision after the reconciliation merge and exact post-merge Quality. It then obtains fresh candidate-specific software evidence, acceptance authority, Vultr read-only preflight, provider proof, Android signing/migration evidence where applicable, physical evidence, recovery evidence and soak evidence.

A protected-main advance after candidate admission invalidates the acceptance window. An ancestor or previously accepted software tree is not sufficient final release authority.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable historical provider-lifecycle proof only. Item 19 is not rewritten as having run on a future SHA, its terminal ownership intent remains terminal, and its candidate-specific evidence is not active Item 20/final-release authority.

## 4. Scope discipline

1. Fix demonstrated production risks, not hypothetical platform requirements.
2. Prefer the smallest complete vertical slice with a tested rollback path.
3. Preserve compatible behavior unless correctness or recovery requires a versioned change.
4. Keep queues, retries, diagnostics, cardinality and side effects explicitly bounded.
5. Keep state ownership singular and machine-readable.
6. Keep public/private/provider/phone trust zones explicit and fail closed on ambiguity.
7. Do not duplicate policy in the private execution satellite when canonical public logic can own it.
8. Do not advance release or physical-acceptance state merely because a software gate is green.
9. Exact historical SHAs are valid in immutable evidence; moving operational “current SHA” claims belong to execution-time resolution or generated/machine-readable state.
10. Current production state is derived only from current scoped `CONTROL` evidence; required durable evidence must be durably persisted before the corresponding state may be promoted.
11. Operation execution result, independent postcondition verification and evidence persistence are separate dimensions. A successful command or workflow does not imply either verified target state or durable proof.
12. `UNKNOWN`, `STALE`, `CONFLICT`, invalid scope, another transaction's evidence and required-but-unpersisted evidence fail closed.
13. No phone, runtime, VM or provider has a stored global `READY` truth. Permission is an operation-specific predicate over exact current facts.
14. Mutation authority is exact-SHA, exact-transaction and exact-boundary scoped. Required phone/device authority is re-proved immediately before destructive work, and a canonical SHA advance invalidates earlier SHA-bound admission for subsequent execution.
15. Recovery, cleanup and quarantine are explicit state paths. A successful recovery does not become acceptance, and already-proven absence must not trigger unnecessary cleanup mutation.
16. The real registered production phone is the authoritative observation oracle for Android device reality. Hosted/offline systems may authorize, transport and validate observations but must not manufacture current Android physical state.
17. If an Android predicate or postcondition can be verified on the real production phone, the dependent production state requires bounded device-backed `CONTROL` evidence from that phone with the scope, freshness and durability required by the operation contract. Unit/integration/hosted-Actions evidence alone cannot complete that Android state.
18. Infrastructure/control-plane hardening may precede a device operation only to remove a demonstrated blocker to the next safe device-backed transition. Once that blocker is closed, execution returns to the real-phone certification path rather than expanding orchestration or framework work without a new demonstrated blocker.

### 4.1 Fact-first state/control contract

The normal production reasoning loop is:

```text
OBSERVE CURRENT FACTS
  -> REDUCE CONTROL STATE
  -> EMIT EXACT BLOCKING PREDICATES
  -> AUTHORIZE ONE NEXT OPERATION
  -> VERIFY PRECONDITIONS
  -> MUTATE ONLY IF AUTHORIZED
  -> INDEPENDENTLY VERIFY POSTCONDITIONS
  -> PERSIST BOUNDED EVIDENCE
  -> REDUCE NEW STATE
```

For a mutating transaction the required lifecycle is:

```text
OBSERVE -> VERIFY -> MUTATE -> INDEPENDENTLY VERIFY -> ACCEPT
                                      |
                                      +-> RECOVER -> RECOVERED | QUARANTINED
```

The reducer, not the workflow conclusion, decides the state. If the device action succeeds but bounded evidence cannot be durably persisted, the resulting state remains explicitly unpersisted/unknown for any guard that requires durable proof. No later operation may reconstruct that missing authority from logs or narrative.

For Android device reality, the observation step above means a bounded authorized observation of the real registered production phone whenever the predicate is technically observable there. A hosted test can prove that an observer or reducer behaves correctly, but cannot substitute for the phone observation that establishes the current device fact.

The public Issue `#179` remains the live execution cursor and authorizes exactly one next transition at a time. The cursor may point to machine evidence, but it does not itself turn narrative into machine truth.

## 5. Completed baseline foundation

The baseline already established the protected application boundaries, SQLite durable-state model, reverse-tunnel correctness controls, backup/restore discipline, GitHub-only execution boundary, typed provider ownership lifecycle and historical Item 19 provider proof. Those historical facts remain subject to their dedicated contracts/evidence and are not restated as current release authority here.

Stable invariants include:

- SQLite is the canonical mutable control-plane store after migration; memory is projection/cache and JSON is migration/diagnostic only;
- no successful acknowledgement precedes durable commit;
- exact replay is idempotent and conflicting idempotency reuse fails closed;
- traffic is never routed to an arbitrary available device when exact device/session authority is required;
- pending work, retries and queues are bounded;
- QUIC is primary, pinned TLS/TCP is reserve and plaintext downgrade is forbidden;
- logs/evidence do not contain credentials, unbounded secret-bearing payloads or raw sensitive device/provider identifiers;
- liveness and serving readiness are separate;
- provider lifecycle uses exact typed ownership/binding semantics and deterministic cleanup;
- the public repository is canonical and the private repository is execution-only;
- control state is a deterministic projection of bounded evidence rather than a manually asserted readiness flag;
- transaction progress cannot be inferred from workflow `success`; execution, postcondition proof and evidence persistence remain independent;
- stale, diagnostic, audit, conflicting or cross-transaction evidence cannot satisfy current mutation guards;
- Android physical-state transitions consume device-backed CONTROL evidence from the real registered production phone whenever the predicate is observable there; hosted evidence proves software/policy, not physical device truth.

## 6. Current Item 20 prerequisites

Item 19 historical provider proof is COMPLETE. Its exact proof record remains in `docs/operations/item19-provider-proof-closeout.md`.

**Item 20 is the first unfinished delivery item.** Item 20 remains blocked by the signing-continuity gate recorded in `docs/operations/phone-gitops-runtime.md` / #115 and by every other still-open prerequisite defined by the canonical Item 20 and Android migration contracts at execution time.

Architecture reconciliation does not reuse the Item 19 candidate. After #172 is merged and exact post-merge `Quality` succeeds, that exact protected public `main` SHA becomes the new active candidate/control-plane identity. Candidate-specific evidence is then built fresh for it.

Before mutable phone work, the private execution satellite must be repinned to that exact public SHA, the exact signed Android candidate must be built and retained with bounded provenance, and the signing-generation migration may run only through the authorized #162 path after all of its prerequisites are actually satisfied. No final `v0.1.4` tag or GitHub Release is an input to that migration.

The phone path must retain and verify the old installed APK/signing generation before uninstall, re-check the registered device immediately before mutation, install only the exact verified candidate and execute the defined rollback path on post-capture failure. No unrelated reboot/network/provider mutation is authorized by the migration.

### 6.1 Current fact-first execution sub-sequence

The immediate product hardening sequence uses Android as the first fully evidenced adapter and closes one verified layer at a time:

1. **Evidence reliability** — close only the demonstrated bounded evidence-persistence blocker; retry persistence transport only when explicitly safe and never replay the phone observation/mutation merely to obtain an artifact.
2. **Current-SHA phone admission** — immediately return to the real registered production phone and prove fresh `PHONE_ACCESS_PROVEN` for the exact current canonical SHA before any dependent Android observation or mutation.
3. **Quarantine reconciliation** — perform one fresh read-only real-phone observation of the exact quarantined transaction IDs named by the current #179 cursor. Durable device facts decide whether cleanup is needed; if the paths are durably proven absent, cleanup is skipped entirely.
4. **Android filesystem certification** — prove current capabilities plus bounded owned scratch and managed-root create/write/read/compare/delete/post-absence behavior and explicit recovery/quarantine semantics from device-backed evidence.
5. **APK/signing lifecycle** — prove exact signed artifact identity, installed baseline, mutation-boundary reproof, uninstall/install separation, independent real-phone signer/version/digest verification and recovery behavior.
6. **Native runtime lifecycle** — prove exact generation materialization, integrity/current binding, start, structural health, functional health, restart/rehydration and recovery on the real phone.
7. **Real data path** — prove control plane -> phone -> QUIC -> protected proxy ports, forced pinned TLS/TCP reserve, and return of new connections to QUIC after recovery.
8. **Restart/recovery/failure matrix** — inject bounded failures at defined boundaries and prove `REFUSED`, `RECOVERY_REQUIRED`, `RECOVERED` or `QUARANTINED` without narrative state promotion.
9. **Soak and release acceptance** — only on one unchanged exact candidate with all required durable device-backed evidence and no unresolved P0/P1 defect.
10. **VM/provider generalization** — only after the phone baseline demonstrates which primitives are genuinely common; reuse proven `observe/guard/lock/mutate/verify/recover/evidence` semantics instead of inventing a speculative second framework.

This is an execution sub-sequence, not permission to skip or reorder stricter Item 20 provider, signing, candidate-acceptance or final-release gates. At every point the exact current `#179` cursor and derived blocking predicates decide the single next safe transition. Infrastructure work inside this sub-sequence exists to unblock the next device-backed step; completion of that infrastructure work is not itself completion of the Android step it enables.

## 7. Item 20 live acceptance

When all prerequisites are satisfied, Item 20 opens a fresh just-in-time acceptance session through the protected typed lifecycle under a **distinct ownership intent rather than reuse Item 19's terminal proof intent**.

The session must use the new exact same-SHA candidate/control-plane identity and fresh candidate-specific authority/evidence. It must prove, as applicable:

- exact deployed identity on phone and server before traffic tests;
- exact Android package/version/signer-match/install state when the topology uses the managed app component;
- primary first-party reverse tunnel over QUIC;
- reboot/restart state rehydration and reconnection;
- forced QUIC failure with certificate-pinned TLS/TCP reserve;
- return of new connections to QUIC after recovery;
- mixed proxy, SOCKS5, HTTP and HTTP CONNECT through the real phone path;
- stock WireGuard rollback and return to primary native ownership;
- recovery/repetition/crash cases required by `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`;
- at least the required 24-hour production-like soak on the same exact candidate;
- exact deployed identity again after transitions;
- no unresolved P0/P1 defect.

A candidate change, protected-main advance or software fix establishes a new software identity and invalidates candidate-specific acceptance evidence as required by the one-SHA rule.

## 8. Final release ordering

Only after successful physical acceptance, create the final immutable release evidence and protected annotated `vMAJOR.MINOR.PATCH` tag, attach the required artifacts/digests and provenance evidence, and publish the release using the approved immutable ordering.

The Item 20 tracker must record exactly one:

```text
final_accepted_candidate_sha: <40 lowercase hexadecimal characters>
```

Final tag creation must independently prove that this SHA still equals exact protected `main`, has exact successful main Quality, satisfies the release version contract and is the tag target. Release publication must derive from that tag target SHA or reuse already accepted immutable artifacts whose digest/provenance proves the same source identity.

Only after the final release exists may production promotion occur through the typed provider path. Manual provider mutation is not a normal promotion or recovery shortcut.

## 9. Required delivery order

The historical completed foundation remains auditable in its own trackers/evidence. The active sequence is:

1. complete #172 architecture/documentation reconciliation in a protected public PR;
2. prove exact PR-head `Quality` success;
3. squash-merge through protected `main` and prove exact post-merge push `Quality` success;
4. select that exact merge SHA as the sole active Item 20 candidate/control-plane identity and freeze source identity for the acceptance window;
5. build fresh exact software release-candidate evidence;
6. obtain fresh `/accept-candidate <sha>` authority;
7. obtain fresh `/vultr-readonly-preflight <sha>` evidence;
8. obtain the fresh exact-candidate provider proof required by the Item 20 contract;
9. repin the private execution satellite to that exact public SHA and keep its wrapper thin;
10. build and retain the exact signed Android `0.1.4` / `1004` candidate and bounded provenance;
11. run the #162 signing-generation migration only when all hard prerequisites pass;
12. prove installed package/version/signer match/runtime and rollback evidence, then close #115/#162 only if their real acceptance criteria are satisfied;
13. open the fresh Item 20 JIT acceptance lifecycle on the same SHA with distinct Item 20 ownership intent;
14. execute physical phone/provider acceptance on that same SHA;
15. execute the recovery/restart/crash repetition matrix on that same SHA;
16. execute the required 24-hour soak on that same SHA;
17. close Item 20 completed and record `final_accepted_candidate_sha` only after all applicable evidence passes;
18. re-prove protected `main` still equals that accepted SHA;
19. issue the owner `/release-tag vX.Y.Z <sha>` command on canonical #90;
20. immutable-SHA physical acceptance on the real phone against a fresh JIT acceptance session created through the protected typed lifecycle;
21. final immutable release evidence, protected annotated release tag and artifacts;
22. Vultr production promotion/deployment from the accepted final release tuple;
23. final baseline closeout only after the documented post-release/production gates pass.

Items 21 and 22 remain forbidden until Item 20 succeeds. No final protected `v*` release/tag or production promotion is authorized by historical Item 19 completion, Android version metadata, a private signed build or architecture reconciliation alone.

The numbered release chain above is preserved as the authority ordering. Section 6.1 controls how unresolved phone/runtime work is proven within that chain: every completed step must be a machine-derived fact before the next dependent transition can execute.

## 10. CI/CD and evidence requirements

Every public source change goes through pull request review, exact immutable PR-head Quality, protected merge and exact post-merge Quality before that SHA may become an active acceptance candidate.

`Quality` must fail closed on:

- candidate/control-plane inequality;
- hardcoded historical Item 19 SHA as active Item 20 candidate;
- final tag target differing from accepted candidate;
- protected-main advancement after acceptance without reacceptance;
- release publication from a different source SHA;
- documentation that makes the Android app globally absent from production;
- private repository policy/source authority;
- future roadmap claiming current operational authority;
- retired two-SHA semantics on active normative surfaces;
- active roadmap wording that permits workflow/job success to substitute for derived CONTROL state or independently verified postconditions;
- active roadmap wording that permits required-but-unpersisted evidence, `UNKNOWN`, stale or cross-transaction evidence to advance production state;
- active roadmap wording that introduces a global phone/VM/provider `READY` flag instead of operation-scoped permission predicates;
- active roadmap wording that removes the real registered production phone as the authoritative observation oracle for Android device reality;
- active roadmap wording that allows hosted/unit/integration evidence alone to complete an Android predicate or postcondition that is verifiable on the real production phone;
- active roadmap sequencing that allows infrastructure/orchestration hardening to continue after its demonstrated device blocker is closed instead of returning to the next real-phone certification step.

Evidence is bounded and immutable. Public evidence may include non-sensitive public SHA/run/artifact identities and booleans required by contract; it must not include credentials, signing secrets/fingerprints, raw device serials, private endpoints or secret-derived identifiers.

When a state transition requires a durable artifact, artifact persistence is part of the admission predicate, not an afterthought. Transport failure during evidence persistence must remain separately classified from the device operation itself and cannot be repaired by inferring durable state from logs.

## 11. Definition of done

### Architecture reconciliation complete

#172 may be closed as architecture/documentation reconciliation only when:

- contracts, docs, workflows, code and tests describe one coherent same-SHA model;
- Android production role is topology-conditional and consistent;
- public/private trust zones are consistent;
- Production Baseline is the sole active roadmap and future documentation is non-operational;
- historical Item 19 evidence remains historical-only;
- a cross-document consistency fitness gate protects these invariants;
- exact PR-head and exact post-merge public `Quality` are successful.

This status must **not** be described as global project 10/10 acceptance.

### Full project 10/10 accepted

Global 10/10 is reached only after the same exact accepted public SHA has all applicable software, provider, Android migration/signing, real-phone, recovery/restart/crash and 24-hour soak evidence; Item 20 is completed; protected `main` still equals that SHA; the final annotated tag targets it; and published artifact provenance is bound to that same source SHA.

Acceptance additionally requires that every production transition used the evidence-derived CONTROL/operation state model: no required state may be promoted solely from workflow conclusion, historical narrative or unpersisted proof. Any Android state or postcondition that is verifiable on the real production phone must be backed by bounded device-backed CONTROL evidence from that phone rather than hosted/offline evidence alone.
