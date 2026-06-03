# VM Runtime Bundle

This directory contains VM-side reproducible runtime inputs.

`bin/sing-box` is intentionally ignored and prepared by:

```bash
cargo run -p operator-cli -- prepare-runtime-binaries
```

`operator-cli provision-vm` builds Rust VM binaries from source, renders configs from environment variables, creates a GCP VM when needed, copies the release over SSH, and enables systemd services.

`operator-cli delete-vm` deletes the VM and, when requested, its generated firewall rules.
