# VM ownership boundary

Status: normative contract for shared-account VM providers
Machine-readable contract: `contracts/governance/vm-ownership-v1.json`

## Purpose

A cloud API credential can enumerate resources that are not owned by this application. A label,
name or a first provider search result is not authority to mutate a VM. This contract prevents a
mobile-proxy provider adapter from operating a neighbouring VM in the same cloud account.

The current `operator-cli` VM adapter targets the dedicated legacy GCP project. A Vultr adapter
does not yet exist. This contract is an activation gate: a shared-account adapter must implement
and test it before exposing lifecycle commands.

## Binding

The application persists one durable, owner-controlled binding outside Git. It contains the
provider-assigned immutable VM UUID and a monotonically increasing generation. The binding is not
reconstructed from a label, an IP address or provider list ordering.

Every owned VM must have these exact provider tags:

```text
project=mobile-proxy
managed-by=mobile-proxy
```

Tags are a second ownership proof; the persisted UUID remains the primary authority. A provider
credential can technically bypass application checks, so it is used only through the adapter and
Secret Vault wrapper.

## Lifecycle rules

| Operation | Required proof and state transition |
| --- | --- |
| Create | Request the tags; re-read the provider response; persist the UUID binding before reporting success. |
| Manage | Read the bound UUID from state; re-read the provider resource; require exact UUID and tags. |
| Snapshot | Use only the verified bound UUID; reject all other resource identifiers. |
| Delete | Re-read and verify the bound UUID and tags; clear the binding only after provider deletion succeeds. |
| Recreate | Create and verify a tagged replacement; atomically replace UUID and generation only after verification. |

The caller never supplies an arbitrary provider instance UUID. The adapter must fail closed on a
missing or invalid binding, an absent provider instance, a UUID mismatch, a missing/mismatched tag,
or a binding compare-and-swap conflict. It must never select a VM by label, name or first match.

## Enforcement

`scripts/check_vm_ownership_contract.py` validates the contract shape and mandatory fail-closed
rules. It runs from the permanent architecture policy check. Provider implementation tests must
exercise every lifecycle rule before a shared-account provider command can be released.
