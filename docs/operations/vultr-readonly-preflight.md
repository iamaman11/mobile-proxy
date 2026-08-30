# Vultr read-only acceptance preflight

Production Baseline item 17 proves only that an immutable accepted candidate can reach the target
Vultr account through GitHub-hosted infrastructure with the required provider API key and bootstrap
SSH private key available. It does not authorize VM lifecycle or final production deployment.

## Command

The repository owner invokes the gate on canonical Issue #90 with exactly:

`/vultr-readonly-preflight <40-character-lowercase-candidate-sha>`

The workflow first verifies a successful `Vultr acceptance authority` run and its exact bounded
artifact for that same candidate SHA. Only then may the `acceptance-vultr` environment expose its
scoped secrets to the provider probe job.

## Allowed provider operation

The item-17 provider surface is exactly one authenticated request:

`GET https://api.vultr.com/v2/account`

The response body is discarded. Provider account fields, key-derived identifiers, SSH public-key
material and secret values are never written to logs, summaries or evidence.

The bounded success artifact records only immutable workflow/candidate identities and boolean
results. It explicitly records that VM lifecycle, VM mutation, phone mutation, final-production
authority and final release creation did not occur.

## Fail-closed boundary

The preflight rejects mutable or approximate candidate identities, missing/mismatched acceptance
evidence, missing credentials, an invalid SSH private key, or a failed account request. The
`acceptance-vultr` environment is distinct from `production-vultr`; using final-production authority
to make pre-release acceptance work is forbidden.

No `/v2/instances` or other VM endpoint, mutating provider method, Vultr CLI, manual SSH, ADB or GCP
operation belongs to this item. Typed UUID/tags/generation-CAS lifecycle begins only in the next
baseline item and VM creation remains forbidden until the later just-in-time acceptance-VM gate.
