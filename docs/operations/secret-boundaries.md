# Secret boundaries

Git is authoritative for secret *names*, ownership and allowed execution boundaries—not secret
values. The exact required names are versioned in
[`github-control-plane-v1.json`](../../contracts/operations/github-control-plane-v1.json).

| Secret class | Permitted location | Forbidden location |
| --- | --- | --- |
| Vultr API and bootstrap SSH key | Encrypted `production-vultr` environment secret consumed by GitHub-hosted job | Public repository, phone runner, workflow output, artifact, Issue |
| Phone control and application credentials | Private phone-control repository environment/secret store | Public source repository and Vultr job |
| Android release signing identity | Private phone-control repository Actions secrets for tagged phone lifecycle; local Secret Vault only for recovery/bootstrap | Public source repository, GitHub Release assets, Issue, log, workflow output or evidence |
| Local recovery credential | Local Secret Vault during bootstrap/recovery only | Git, runtime artifact and standard production workflow |

Secrets must be passed directly to the consuming process, never rendered into generated source,
configuration committed to Git, command output or evidence. A possible secret-scanning alert is a
potential disclosure: revoke/rotate at the provider before rewriting history or deleting files.
