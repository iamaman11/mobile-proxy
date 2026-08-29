## Change

Describe the user-visible or operational outcome.

## Architecture impact

- New crate/module/service/runtime component: no / yes — explain if yes
- New internal dependency edge or production dependency: no / yes — explain if yes
- New authoritative state/schema/background work/public contract: no / yes — explain if yes
- Complexity added:
- Complexity removed:
- Simpler alternative considered and why insufficient:
- State/behavior owner:
- Rollback/deletion path:
- ADR: not required / path

Architecture-significant changes must follow `docs/architecture/ARCHITECTURE_STANDARD.md` and keep `contracts/governance/module-boundaries-v1.json` exact.

## Risk and rollback

- Risk:
- Rollback:

## Evidence

- [ ] Python architecture and regression tests
- [ ] Rust formatting, strict Clippy and workspace tests
- [ ] Android checks when Android code or shared contracts changed
- [ ] Live phone/VM evidence when deployment behavior changed

Production deployment must reference a published annotated tag. Do not paste secrets or large raw logs into the pull request.
