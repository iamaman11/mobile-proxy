# ADR-004 — Production evidence-domain separation

Status: **accepted when merged**  
Scope: PHONE + VM production validation architecture  
Stage sequencing owner: `docs/PRODUCTION_STAGE_ROADMAP.md`

## Context

Production validation had begun to overload one phone Release-observation path with unrelated live operational checks. A failure in a new BusyBox/process-count/runtime-health probe then risked obscuring an already-proven exact Release-state result.

The deeper issue is architectural: transport reachability, immutable Release state, live runtime health, lifecycle perturbation and complete PHONE+VM product health have different owners, lifecycles and failure modes. Treating them as one `READY` value creates false coupling and makes evidence hard to interpret.

The project also cannot honestly claim complete proxy reliability from phone-only load/soak before the real VM/remote-consumer path exists.

## Decision

Production evidence is separated into five domains:

```text
transport readiness
  != exact Release state
  != live operational state
  != lifecycle exercise result
  != full-topology state
```

### 1. Transport readiness

Proves only the admitted control path to a registered target, such as runner/host/USB/ADB/root readiness for `phone-production`.

Transport degradation does not imply Product Release mismatch or PRODUCT runtime failure.

### 2. Exact Release state

Proves exact immutable target state required by the Product Release contract. For the phone this includes the admitted APK + rooted-runtime/current truth.

Deployment postcondition, normal Release observation and target-read-only reconciliation may share this concrete truth where they require the same facts.

### 3. Live operational state

Proves whether an accepted target is currently operational using the smallest owning health/readiness contracts and bounded target facts.

For the phone this may include `runtime-supervisor`, `host-daemon`, `sing-box`, authenticated local PRODUCT health, serving/cellular prerequisites and bounded resource indicators.

Operational observation is read-only and independently classified. `DEGRADED` or `UNKNOWN` live health does not rewrite an independently exact immutable Release-state result.

Controller observation consumes PRODUCT-owned health semantics where available; it does not reimplement PRODUCT health computation.

### 4. Lifecycle exercise result

A process termination, runtime restart, phone reboot, VM restart or mismatch drill is a separately admitted perturbation with a fixed scenario, identity, timeout, postcondition and recovery policy.

Lifecycle exercises are not free-form ADB/shell surfaces and are not ordinary observation.

### 5. Full-topology state

Full product acceptance exists only on the real production path:

```text
external consumer
  -> VM / relay / serving edge
  -> authenticated reverse tunnel
  -> registered phone runtime
  -> mobile/cellular egress
  -> Internet
```

Remote HTTP CONNECT/SOCKS5 behavior, external mobile-egress identity, DNS/IPv6/leak policy, production QUIC/reserve behavior, cross-target recovery, production-scale load and long soak are accepted only when that complete path exists.

## Stage consequence

- Stage 4 proves the phone as an independently exact, locally operational, observable and recoverable production node with bounded local resource sanity.
- Stage 5 simplifies/converges the proven phone baseline without collapsing independent evidence domains merely to reduce command count.
- Stage 6 creates and accepts the real VM target and is the first normal point for shared phone/VM abstractions from demonstrated duplication.
- Stage 7 proves the complete PHONE+VM product/topology under real external serving, network behavior, cross-target failures, production load and soak.

The canonical sequencing and exit definitions remain owned only by `docs/PRODUCTION_STAGE_ROADMAP.md`.

## Consequences

Positive:

- failures are classified by the responsibility that actually failed;
- S4.3 exact-state evidence cannot be accidentally invalidated by new S4.4 operational probes;
- operator surfaces can remain small without becoming semantically overloaded;
- expensive load/soak work is executed against the workload it is intended to prove;
- phone/VM shared abstractions are derived from two real implementations, not speculation.

Costs:

- multiple read-only/operator surfaces may remain when they have independent operational purpose;
- evidence consumers must preserve domain labels instead of flattening everything into one success bit;
- Stage 7 carries the expensive full-system reliability matrix because that is the first stage where the product actually exists end-to-end.

## Rejected alternatives

### One universal phone observer

Rejected because immutable Release truth and live operational health change on different causes and can fail independently.

### Open VM work in the middle of Stage 4

Rejected because it creates cyclic stage dependencies and multiple active-looking execution plans. The stage boundary is corrected instead: Stage 4 proves the phone node, Stage 6 creates the VM, Stage 7 proves the combined system.

### Full phone-only production soak before VM

Rejected as insufficient evidence for the product's real workload. Stage 4 retains bounded phone-local resource sanity; complete long soak belongs to Stage 7.
