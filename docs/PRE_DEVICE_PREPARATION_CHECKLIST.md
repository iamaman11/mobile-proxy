# Pre-Device Preparation Checklist

> **STATUS: CURRENT PREPARATION GATE**
>
> This checklist covers work that can be completed before a real rooted Android phone is connected.
> It does not replace `docs/physical-phone-acceptance-runbook.md` and does not authorize rebuilding or
> changing the frozen runtime candidate.

## 1. Frozen candidate and evidence

- [ ] Use runtime candidate SHA `778c9a6260f58ede0f5a337c5107bc96b022373c`.
- [ ] Download artifact `software-release-candidate-778c9a6260f58ede0f5a337c5107bc96b022373c`.
- [ ] Record artifact ID `8613999700`.
- [ ] Verify artifact digest
      `sha256:ee084d1a018eee575f77a4f80fc8fc4a1345f105f62f59471abc5503c7bcfe86`.
- [ ] Confirm evidence `format_version=2`.
- [ ] Confirm `software_10_of_10_ready=true`.
- [ ] Confirm `physical_phone_acceptance_required=true`.
- [ ] Confirm `baseline_complete=false`.
- [ ] Create a clean detached checkout of the exact candidate.
- [ ] Confirm the checkout is clean.
- [ ] Do not use the documentation-bearing `main` checkout to build the frozen runtime.

Suggested verification:

```bash
git fetch --all --tags
git checkout --detach 778c9a6260f58ede0f5a337c5107bc96b022373c
test "$(git rev-parse HEAD)" = "778c9a6260f58ede0f5a337c5107bc96b022373c"
test -z "$(git status --porcelain)"
python3 -m json.tool release-candidate-evidence.json >/dev/null
```

## 2. Decide the exact phone before installation

Record before the run:

- [ ] manufacturer and model;
- [ ] Android version and build fingerprint;
- [ ] bootloader/root method;
- [ ] modem/baseband version;
- [ ] SIM operator and PLMN;
- [ ] whether the phone is single-SIM or dual-SIM;
- [ ] expected cellular interface name;
- [ ] ADB serial.

### Mandatory ABI stop condition

The frozen candidate prepares Android Rust and sing-box binaries for 32-bit ARM. Before attempting
installation, verify that the selected phone can execute `armeabi-v7a` binaries:

```bash
adb -s <adb-serial> shell getprop ro.product.cpu.abilist
adb -s <adb-serial> shell getprop ro.product.cpu.abi
```

- [ ] `ro.product.cpu.abilist` includes `armeabi-v7a`, or the device is otherwise proven to execute
      32-bit ARM binaries.
- [ ] If the phone is 64-bit-only, **stop**. Do not attempt the frozen candidate. Implement and test
      `aarch64-linux-android`, produce a new immutable candidate and regenerate all evidence.

## 3. Phone prerequisites to arrange

These can be arranged in advance but are proven only when the phone is available:

- [ ] bootloader unlock/root procedure is documented for the exact model and Android build;
- [ ] Magisk or the selected root mechanism is available;
- [ ] USB debugging is enabled;
- [ ] workstation ADB authorization is possible;
- [ ] no enterprise policy prevents root, airplane-mode control or mobile-data control;
- [ ] suitable active SIM and data plan are available;
- [ ] tethering/VPN/operator restrictions are understood;
- [ ] stock WireGuard Android package `com.wireguard.android` is available for the rollback stage;
- [ ] rollback tunnel name will be exactly `WiGandroid`;
- [ ] Android VPN consent can be granted during rollback testing.

Required proof after connection:

```bash
adb -s <adb-serial> shell su 0 sh -c id
```

Expected result includes `uid=0`.

## 4. Workstation readiness

- [ ] Git is available.
- [ ] Rust toolchain and Cargo are available.
- [ ] required Rust targets and Android NDK are available.
- [ ] Python 3 is available.
- [ ] ADB is available.
- [ ] `gcloud` is installed and authenticated to the correct project.
- [ ] SSH key exists at the path used by the VM manifest/runbook.
- [ ] `curl`, OpenSSL and JSON tooling are available.
- [ ] workstation time is synchronized.
- [ ] sufficient disk space exists for immutable device/VM release roots and reports.
- [ ] a dedicated evidence directory exists with restrictive permissions.

## 5. Device and VM manifests

### Device manifest

- [ ] unique stable device ID selected;
- [ ] node name selected;
- [ ] relay host is correct;
- [ ] control-plane URL is correct;
- [ ] operator profile is selected;
- [ ] every secret references an environment-variable name rather than a literal secret;
- [ ] reverse-tunnel certificate pin is available;
- [ ] no unresolved placeholder remains.

### VM manifest

- [ ] GCP project is correct;
- [ ] zone is correct;
- [ ] instance name is correct;
- [ ] machine type is sufficient;
- [ ] static external IP is reserved;
- [ ] network and target tags are correct;
- [ ] WireGuard rollback addresses and keys are prepared;
- [ ] all secret environment-variable names are correct;
- [ ] SSH user and absolute SSH key path are recorded.

## 6. Secret inventory

Use distinct values for distinct trust roles:

- [ ] host-daemon admin token;
- [ ] control-plane admin token;
- [ ] device token;
- [ ] proxy username;
- [ ] proxy password;
- [ ] reverse-tunnel certificate DER/base64;
- [ ] reverse-tunnel private key DER/base64;
- [ ] WireGuard server private key;
- [ ] WireGuard phone public/private key material as required by the rollback setup.

Rules:

- [ ] secrets exist only in protected environment/files;
- [ ] no secret is committed;
- [ ] no secret is placed in a command-line URL;
- [ ] no secret is copied into reports;
- [ ] admin, device and proxy credentials are not reused;
- [ ] a secure offline recovery copy exists where operationally required.

## 7. Relay name, certificates and controlled probes

- [ ] `mobile-proxy-relay` resolves to the intended relay VM from the workstation and phone path.
- [ ] control-plane public PEM certificate is copied to the workstation.
- [ ] `SSL_CERT_FILE` points to that certificate for the run.
- [ ] controlled HTTP probe endpoint is available.
- [ ] controlled HTTPS probe endpoint is available.
- [ ] probes return deterministic bounded responses.
- [ ] probes do not expose tester credentials.
- [ ] an external test client/network is available to validate public proxy ports.

## 8. VM preparation that does not require the phone

- [ ] VM can be provisioned from the frozen candidate.
- [ ] provisioning is repeatable and idempotent.
- [ ] Nginx configuration passes `nginx -t`.
- [ ] control-plane, reverse-tunnel-server, relay-gate and Nginx start successfully.
- [ ] SQLite migration and restart preserve state.
- [ ] SQLite backup and clean restore drill passes.
- [ ] public listeners match the runbook.
- [ ] QUIC UDP `18090` is reachable as designed.
- [ ] pinned TLS/TCP reserve `443` is reachable as designed.
- [ ] control-plane TLS endpoint `8443` is reachable as designed.
- [ ] proxy ports `1080`, `1081` and `3128` are reachable only as intended.
- [ ] VM static package files match the immutable VM release package.
- [ ] native and WireGuard Nginx switch configurations are known and byte-verifiable.
- [ ] a documented method exists to block only QUIC UDP `18090` during fallback testing.
- [ ] a documented method exists to remove that block and terminate the reserve connection.

## 9. Build immutable release variants before the sequence

From the frozen clean checkout:

- [ ] prepare architecture-correct runtime binaries;
- [ ] package native `first_party_reverse_tunnel` phone release;
- [ ] package `stock_wireguard_bridge` rollback phone release;
- [ ] package/provision the VM release;
- [ ] verify every BLAKE3 integrity manifest;
- [ ] verify release metadata contains the exact frozen SHA;
- [ ] make release roots read-only for the duration of acceptance;
- [ ] do not rebuild any variant during the physical sequence.

Recommended release IDs:

```bash
RELEASE_BASE="physical-778c9a6"
REVERSE_RELEASE="${RELEASE_BASE}-reverse"
WIREGUARD_RELEASE="${RELEASE_BASE}-wireguard"
VM_RELEASE="${RELEASE_BASE}-vm"
```

## 10. Evidence workspace

Prepare empty paths for all required reports:

- [ ] `physical-vm-primary-switch.json`
- [ ] `physical-primary-deployment.json`
- [ ] `physical-online.json`
- [ ] `physical-post-reboot.json`
- [ ] `physical-fallback.json`
- [ ] `physical-recovered.json`
- [ ] `physical-vm-wireguard-switch.json`
- [ ] `physical-wireguard-deployment.json`
- [ ] `physical-wireguard.json`
- [ ] `physical-vm-reverse-switch.json`
- [ ] `physical-reverse-activation.json`
- [ ] `physical-final-deployment.json`
- [ ] `physical-post-wireguard-recovered.json`
- [ ] `physical-acceptance-summary.json`

Also record outside secret-bearing logs:

- [ ] tester identity;
- [ ] UTC start/end timestamps;
- [ ] phone model/build/operator;
- [ ] VM project/zone/instance/static IP;
- [ ] candidate SHA, workflow IDs, artifact ID and digest.

## 11. Dry checks before connecting the phone

- [ ] every acceptance script parses and displays help successfully;
- [ ] report validators reject incomplete synthetic report sets;
- [ ] wrong certificate is rejected in a controlled software test;
- [ ] wrong tokens and proxy credentials fail without reflecting secrets;
- [ ] VM native/WireGuard/native switches are transactional and reversible;
- [ ] backup restoration is proven on a clean path;
- [ ] no unresolved P0/P1 defect exists for the frozen candidate;
- [ ] future roadmap items are not accidentally treated as already implemented.

## 12. What cannot be completed without the real phone

The following are the physical acceptance itself, not remaining software preparation:

- root proof on the exact phone;
- installation and byte comparison on the phone;
- Magisk boot-hook behavior;
- real modem and carrier routing;
- real cellular public egress;
- full phone reboot recovery;
- carrier behavior for QUIC and TLS/TCP reserve;
- Android VPN ownership during stock WireGuard rollback;
- disappearance of `tun0` after native restoration;
- phone/operator-specific rotation timing;
- repeated destructive recovery matrix;
- 24-hour production-like soak.

## 13. Ready-to-connect decision

The project is ready to connect the phone when:

1. frozen candidate/evidence are verified;
2. the exact phone is selected and is compatible with the candidate ABI;
3. all manifests, secrets, certificates, VM resources and controlled probes are ready;
4. immutable native, rollback and VM releases are built and verified;
5. evidence paths and operational stop conditions are prepared;
6. no runtime source or packaged artifact has changed.
