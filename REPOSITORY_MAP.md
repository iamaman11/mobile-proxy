# Repository Map

Date: 2026-06-02
Workspace: `/home/bose/projects/mobile-proxy`

## Goal

This repository must be readable as a layered system, not as a pile of scripts and binaries.

The working rule is simple:
- shared contracts live in `crates/`
- executable products live in `apps/` and `services/`
- deployable runtime bundles live in `deploy/`
- local/operator automation lives in `apps/operator-cli`
- architecture and operations documents live as root-level `*.md` files

## Current Top-Level Ownership

- `crates/proxy-core`
  - shared contracts, enums, DTOs, runtime projection rules, default rotate settings
  - now split into `constants`, `runtime`, `commands`, `records`, and `endpoints`
  - this is the current source of truth for cross-service API shapes

- `services/host-daemon`
  - phone-local runtime API, rotation executor, control-plane sync, and health probe
  - now split into focused modules for `api`, `auth`, `config`, `rotation`, `control_plane`, `health`, and `state`
  - health is fail-closed and policy-routing aware: a cellular default route in Android policy tables counts as route-ready, but serving is not accepted without proxy bind and public observer success

- `services/control-plane`
  - VM-side registry, desired-state, command queue baseline
  - now split into focused modules for `routes`, `projection`, `cli`, and `state`
  - target state remains durable control-plane with persistence and restart recovery

- `services/relay-gate`
  - VM-side public readiness/probe gate
  - should stay narrowly focused on public exposure and probe reporting

- `apps/operator-cli`
  - operator-facing Rust CLI
  - now split into `cli`, `commands`, and `http`
  - target home for provision, verify, rotate, rollback, fleet, and timing-study commands

- `crates/runtime-domain`
  - pure runtime state machine baseline
  - current home for deterministic runtime transition logic

- `crates/reverse-tunnel`
  - first-party Rust userspace reverse tunnel core
  - current PoC covers reconnect after server drop, reconnect after VM listener restart, and stable session identity
  - target home for transport framing, heartbeat, reconnect policy, and stream contracts before VM/phone service integration

- `services/runtime-supervisor`
  - phone-side supervision process
  - owns `host-daemon` and `sing-box` lifecycle, health reconciliation, WireGuard kick attempts, route repair attempts, and data-bounce fallback

- `apps/android-app`
  - thin Android shell only
  - should not become the primary home for business logic

- `deploy/device-runtime`
  - phone runtime bundle layout, Magisk bootstrap, config templates, release payload structure
  - `service.sh` is bootstrap-only and starts the versioned Rust supervisor

- `deploy/manifests/devices`
  - per-device declarations and rollout inputs

- `config/*.example.env`
  - local environment examples for services and operators

- root `*.md` documents
  - repository map, architecture plan, runtime layout, quick reference

## Required Layering

### Layer 1. Domain

Purpose:
- pure rules
- state transitions
- intent derivation
- failure classification

Placement:
- target new crates under `crates/`, for example:
  - `crates/runtime-domain`
  - `crates/control-domain`

Rule:
- no shell calls
- no HTTP
- no file IO
- deterministic tests only

### Layer 2. Application

Purpose:
- orchestrate workflows
- run state machines
- sequence retries, deadlines, and reconciliation loops

Placement:
- service-local modules or dedicated crates, for example:
  - `services/runtime-supervisor`
  - `services/control-plane`
  - `apps/operator-cli`

Rule:
- depends on domain
- issues commands to infrastructure
- owns use cases, not OS-specific details

### Layer 3. Infrastructure

Purpose:
- Android/system calls
- HTTP adapters
- persistence
- process supervision
- route inspection and repair

Placement:
- target new crates or service modules, for example:
  - `crates/android-infra`
  - `crates/control-plane-store`
  - `crates/runtime-probes`

Rule:
- hide platform details behind typed interfaces
- keep translation code local

### Layer 4. Delivery and Deploy

Purpose:
- package binaries
- version configs
- deploy to VM and phone
- bootstrap startup hooks

Placement:
- `deploy/`
- `apps/operator-cli`

Rule:
- deployment layout must not become a source of business logic

## Where To Put New Code

- new shared request/response types: `crates/proxy-core`
- new pure runtime state machine: new crate under `crates/`
- new reverse-tunnel protocol or reconnect policy: `crates/reverse-tunnel`
- new VM registry persistence: crate under `crates/` or focused module inside `services/control-plane`
- new phone supervision loop: `services/runtime-supervisor`
- new operator commands: `apps/operator-cli`
- new deployment template or bundle artifact: `deploy/`
- temporary/manual ops workaround: add an `operator-cli` command or a documented root-level runbook; do not add new persistent shell/PowerShell automation

## Naming Rules

- `proxy-core`: shared contracts only
- `*-domain`: pure logic only
- `*-infra`: OS/network/process/storage adapters
- `*-supervisor`: long-running orchestration process
- `operator-cli`: human-operated entrypoint
- `relay-gate`: public readiness gate only

## Local Directory Rules

The root should stay easy to scan.

Allowed top-level groups:
- `apps/`
- `crates/`
- `services/`
- `deploy/`
- `config/`
- root `*.md` docs

Do not add new top-level folders for one-off experiments.
Put experiments under one of:
- a dedicated crate/app/service if it is real product code
- a root markdown document if it is architecture or operations knowledge

## Codebase Findings That Must Be Fixed

The major monolithic `main.rs` problem has been reduced further, but structural work is not finished.

Concrete problems:
- `crates/proxy-core` still contains projection policy together with shared contracts
- `services/runtime-supervisor` is now the real phone-side process supervisor, but it still needs live reboot/airplane/kill validation on the phone
- phone packaging/install/verify/rollback have Rust CLI coverage
- VM from-zero provisioning has Rust CLI coverage
- control-plane now has JSON-backed restart persistence; stronger transactional storage remains a future hardening step
- device-runtime convergence still depends on live cellular/SIM availability

Corrective rule:
- one file or module should have one clear responsibility
- each executable should keep `main.rs` as composition root only
- domain policy should move into dedicated crates/modules, not stay embedded in HTTP binaries

## Immediate Cleanup Standard

From this point forward:
- architecture and ops documents stay at repository root
- root markdown files are the only place for persistent repo documentation
- runtime policy must stay out of `service.sh`; persistent PowerShell operator automation is no longer part of the active tree
- persistent `*.ps1` operator scripts have been removed from the active tree
- each new responsibility must have one obvious owner directory
- each executable should be split into `config`, `state`, `api`, `application`, and `infra` modules before it grows further
