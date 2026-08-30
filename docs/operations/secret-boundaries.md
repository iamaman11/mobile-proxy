# Secret boundaries

Git is authoritative for secret *names*, ownership and allowed execution boundaries—not secret
values. The exact required names are versioned in
[`github-control-plane-v1.json`](../../contracts/operations/github-control-plane-v1.json).

| Secret class | Permitted location | Forbidden location |
| --- | --- | --- |
| Vultr pre-release acceptance API and bootstrap SSH key | Encrypted `acceptance-vultr` environment secrets consumed only by a GitHub-hosted job after exact immutable acceptance-authority evidence is verified; item 17 permits only credential presence/key parsing and one read-only `GET /v2/account` request | Public repository, phone runner, workflow output, artifact, Issue, `production-vultr` as an acceptance shortcut, any VM lifecycle before item 18 |
| Vultr final-production API and bootstrap SSH key | Encrypted `production-vultr` environment secrets consumed only by GitHub-hosted final-production jobs after the protected final `v*` release gate | Pre-release acceptance workflow, public repository, phone runner, workflow output, artifact, Issue |
| Phone control and application credentials | Private phone-control repository environment/secret store | Public source repository and Vultr job |
| Android release signing identity | Private phone-control repository Actions secrets for tagged phone lifecycle; local Secret Vault only for recovery/bootstrap | Public source repository, GitHub Release assets, Issue, log, workflow output or evidence |
| Local recovery credential | Local Secret Vault during bootstrap/recovery only | Git, runtime artifact and standard production workflow |

`acceptance-vultr` and `production-vultr` are intentionally separate authority boundaries even when
they use the same required secret names (`VULTR_API_KEY` and `VULTR_SSH_PRIVATE_KEY`). Copying a
credential into the acceptance environment does not grant final production authority, and using the
production environment to bypass the acceptance boundary is forbidden.

The item-17 acceptance job must discard the `/v2/account` response body. It may record only bounded
booleans and immutable workflow/candidate identities; provider account fields, SSH public-key
material, credential-derived identifiers and raw errors that could contain sensitive data are not
evidence.

Secrets must be passed directly to the consuming process, never rendered into generated source,
configuration committed to Git, command output or evidence. A possible secret-scanning alert is a
potential disclosure: revoke/rotate at the provider before rewriting history or deleting files.
