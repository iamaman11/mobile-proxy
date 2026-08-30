# Operations contracts

This directory contains bounded machine-readable operational contracts. The pre-release Vultr path
is deliberately split into two stages before provider lifecycle exists:

1. `acceptance-authority-v1.json` proves immutable candidate authority without provider secrets.
2. `vultr-readonly-preflight-v1.json` permits only GitHub-hosted credential/key validation and one
   read-only `GET /v2/account` probe in the separate `acceptance-vultr` environment.

Neither contract grants final production authority. `production-vultr` remains protected by the
final protected `v*` release gate, and VM lifecycle remains unavailable until its later typed
ownership contract is implemented and verified.
