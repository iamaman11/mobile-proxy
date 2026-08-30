# VM ownership boundary

Status: normative contract for shared-account VM providers
Machine-readable contract: `contracts/governance/vm-ownership-v1.json`

## Purpose

A cloud API credential can enumerate resources that are not owned by this application. A label,
name, IP address, prefix match or first provider search result is not authority to mutate a VM.
This contract prevents a mobile-proxy provider adapter from operating a neighbouring VM in the
same cloud account.

The provider-neutral lifecycle policy lives in `crates/proxy-core/src/provider_lifecycle.rs`.
Vultr HTTP/DTO/tag translation lives behind the isolated
`apps/operator-cli/src/vultr_lifecycle.rs` adapter boundary. Provider-neutral code does not depend
on Vultr response shapes or endpoint details.

Item 18 implements and permanently tests this control policy, but it does **not** expose live Vultr
lifecycle execution. The first real JIT acceptance VM is item 19.

## Binding and exact ownership intent

The application lifecycle boundary requires one durable, owner-controlled binding outside version
control. The binding contains:

- the provider-assigned immutable VM UUID/ID;
- the exact lifecycle `scope` (`acceptance` or `production`);
- an exact immutable `intent` ID for the deployment/acceptance intent;
- a positive monotonically increasing `generation`.

The binding is not reconstructed from a label, name, IP address, provider list ordering or a
caller-supplied UUID. The lifecycle store is represented by the `VmBindingStore` port and every
binding create, replacement or clear is a compare-and-swap against the exact expected prior
binding/generation. A stale actor therefore cannot mutate or replace a newer binding.

Every owned Vultr VM carries exact provider tags encoding the complete ownership tuple:

```text
mobile-proxy:project=mobile-proxy
mobile-proxy:managed-by=mobile-proxy
mobile-proxy:scope=<exact scope>
mobile-proxy:intent=<exact immutable intent ID>
mobile-proxy:generation=<exact positive generation>
```

All five ownership fields are exact. Fuzzy matching, prefix matching, partial ownership metadata,
duplicate ownership keys and conflicting ownership metadata fail closed. Unrelated provider tags
may coexist, but they never grant authority.

## Provider-neutral resolution

`ProviderResourceId`, `OwnershipIntent`, `Generation`, `VmBinding` and
`VerifiedMutationTarget` are typed values. Destructive adapter request builders do not accept an
arbitrary provider UUID string: they require a `VerifiedMutationTarget`, whose constructor is
private to the provider-neutral verifier.

For a bound resource, resolution requires all of the following before a mutation target exists:

1. the caller supplies the exact expected generation;
2. expected generation equals the persisted binding generation;
3. exactly one resource claims the exact project/manager/scope/intent tuple;
4. that resource has the exact provider UUID/ID in the binding;
5. its complete ownership metadata, including generation, equals the binding.

Resolution fails closed for zero valid resources, multiple ownership-compatible resources,
duplicate claims, a neighbouring or unbound resource, missing/conflicting metadata, wrong UUID,
wrong ownership or stale generation. A same-name resource with the wrong owner is a neighbour, not
a fallback target.

## Lifecycle rules

| Operation | Required proof and state transition |
| --- | --- |
| Create | Only from a clean unbound reconcile plan with zero ownership-compatible resources. Request exact ownership metadata, verify the returned immutable provider identity and exact metadata, then CAS-persist the initial generation before success. |
| Manage | Resolve the persisted binding and require exact UUID/ID, exact ownership metadata and exact expected generation. |
| Stop | Same verified mutation target as manage; no raw provider identifier is accepted by the adapter. |
| Reconfigure | Same verified mutation target as manage; preserved ownership metadata remains exact. |
| Snapshot | Same verified mutation target as manage; snapshot request derives the provider identity only from the verified target. |
| Delete | Re-read/resolve the verified target, delete only that provider UUID/ID, and clear the binding only after provider confirmation using CAS. |
| Replace | Verify the current target, create a replacement tagged with exactly `generation + 1`, verify it, then atomically CAS the provider identity and generation. |

Reconcile is idempotent: when the exact bound provider identity, exact ownership tuple and desired
spec fingerprint already match, the plan is `Noop`. An unbound but ownership-compatible resource
is not silently adopted, and duplicate ownership claims never trigger another create.

## Vultr adapter boundary

Vultr instance IDs are parsed as UUIDs before becoming `ProviderResourceId`. Vultr's string `tags`
array is translated into the provider-neutral ownership observation; provider-neutral policy never
sees raw Vultr HTTP shapes. Mutation request builders require either a provider-neutral
`PlannedCreate` or `VerifiedMutationTarget`.

The adapter models the current Vultr v2 lifecycle endpoints needed by later items, including list,
create, halt, instance update/delete and snapshots. In item 18 these are typed request descriptors
and unit-test inputs only: no workflow or CLI command obtains Vultr credentials or executes those
mutating requests.

## Item 18 execution boundary

Item 18 is deliberately non-mutating:

- live provider mutation = false;
- real VM creation = false;
- `production-vultr` authority = false;
- phone mutation = false;
- acceptance-vultr remains limited to the already-proven read-only preflight.

The permanent architecture checker validates this boundary and the adapter contains an explicit
item-18 live-execution rejection. Item 19 is the first item permitted to wire controlled JIT
acceptance VM execution through this typed lifecycle path.

## Enforcement

`scripts/check_vm_ownership_contract.py` validates the exact contract shape, implementation
separation and item-18 no-live-mutation boundary. `scripts/tests/test_vm_ownership_contract.py`
permanently rejects policy weakening. Rust tests exercise ambiguous resources, neighbouring
resources, same-name/wrong-owner resources, correct ownership with wrong UUID, missing/conflicting
ownership, duplicate ownership claims, stale generation, CAS conflict, idempotent reconcile and
Vultr exact-tag/UUID mapping.
