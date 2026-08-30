use anyhow::{Context, Result, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use clap::{Parser, Subcommand};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use operator_cli::github_vm_binding_store::{
    AcceptanceVmLifecycleState, DurableGitHubVmBindingStore,
};
use operator_cli::vultr_client::{VultrAcceptanceClient, VultrClientError};
use operator_cli::vultr_lifecycle::VultrVmSpec;
use proxy_core::provider_create_dispatch::{
    CreateRecovery, create_dispatch_fence, create_dispatch_fence_for_recovery,
    recover_dispatched_create,
};
use proxy_core::{
    DesiredVm, Generation, LifecycleError, LifecycleScope, MutationKind, OwnershipIntent,
    ReconcilePlan, VerifiedMutationTarget, VmBinding, VmBindingStore, authorize_mutation,
    plan_present,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::net::Ipv4Addr;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::Duration;

const CANONICAL_REPOSITORY: &str = "iamaman11/mobile-proxy";
const ADMISSION_AUTHORITY: &str = "item19_pre_release_acceptance_lifecycle";
const ACCEPTANCE_ENVIRONMENT: &str = "acceptance-vultr";
const ITEM19_ISSUE: u64 = 124;
const SIGNING_GATE_ISSUE: u64 = 115;
const ACCEPTANCE_REGION: &str = "waw";
const ACCEPTANCE_PLAN: &str = "vc2-1c-2gb";
const ACCEPTANCE_OS_ID: u64 = 2284;
const ACCEPTANCE_LABEL: &str = "mobile-proxy-acceptance";
const MANIFEST_NAME: &str = "manifest.json";
const MANIFEST_FORMAT_VERSION: u32 = 1;
const MAX_JSON_BYTES: u64 = 1024 * 1024;
const MAX_ARTIFACT_FILE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_PUBLIC_KEY_BYTES: usize = 16 * 1024;
const PROVIDER_RECOVERY_ATTEMPTS: usize = 20;
const PROVIDER_RECOVERY_DELAY: Duration = Duration::from_secs(3);
const SSH_READY_ATTEMPTS: usize = 40;
const SSH_READY_DELAY: Duration = Duration::from_secs(3);
const DELETE_CONFIRM_ATTEMPTS: usize = 40;
const DELETE_CONFIRM_DELAY: Duration = Duration::from_secs(3);
const REMOTE_ROOT_PREFIX: &str = "/opt/mobile-proxy-item19";
const ARTIFACT_DIGEST_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/item19-server-artifact-file/v1");
const REQUIRED_ARTIFACT_FILES: [&str; 4] = [
    "bin/control-plane",
    "bin/relay-gate",
    "bin/reverse-tunnel-server",
    "bin/item19-acceptance-lifecycle",
];

#[derive(Parser)]
#[command(name = "item19-acceptance-lifecycle")]
struct Cli {
    #[command(subcommand)]
    command: LifecycleCommand,
}

#[derive(Subcommand)]
enum LifecycleCommand {
    PrepareArtifact {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        root: PathBuf,
        #[arg(long)]
        manifest: PathBuf,
    },
    VerifyArtifact {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        root: PathBuf,
        #[arg(long)]
        manifest: PathBuf,
    },
    ReconcileDeploy {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        admission_evidence: PathBuf,
        #[arg(long)]
        artifact_root: PathBuf,
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        ssh_private_key: PathBuf,
        #[arg(long)]
        evidence_output: PathBuf,
    },
    Cleanup {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        evidence_output: PathBuf,
    },
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct ArtifactEntry {
    path: String,
    size_bytes: u64,
    digest: ContentDigest,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct ArtifactManifest {
    format_version: u32,
    candidate_sha: String,
    digest_domain: String,
    files: Vec<ArtifactEntry>,
}

#[derive(Debug, Deserialize)]
struct AdmissionEvidence {
    format_version: u32,
    authority: String,
    candidate_sha: String,
    repository: String,
    workflow_run_id: String,
    workflow_run_attempt: String,
    command_issue: u64,
    command_comment_id: String,
    quality_run_id: String,
    quality_run_attempt: String,
    acceptance_run_id: String,
    acceptance_run_attempt: String,
    preflight_run_id: String,
    preflight_run_attempt: String,
    physical_acceptance_window_ready: bool,
    signing_continuity_gate_issue: u64,
    signing_continuity_gate_closed: bool,
    scope: String,
    environment: String,
    final_production_authority: bool,
    production_environment_authorized: bool,
    phone_mutation_authorized: bool,
    provider_mutation_performed_at_admission: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BindOrigin {
    Existing,
    Created,
    Recovered,
}

impl BindOrigin {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Existing => "existing",
            Self::Created => "created",
            Self::Recovered => "recovered",
        }
    }
}

#[derive(Serialize)]
struct DeployEvidence<'a> {
    format_version: u32,
    candidate_sha: &'a str,
    scope: &'static str,
    lifecycle_result: &'static str,
    binding_origin: &'static str,
    generation: u64,
    artifact_verified_before_transport: bool,
    deployed_artifact_verified_on_target: bool,
    transport_endpoint_recorded: bool,
    provider_identifier_recorded: bool,
    secret_values_recorded: bool,
    final_production_authority: bool,
    production_environment_authorized: bool,
    phone_mutation_performed: bool,
}

#[derive(Serialize)]
struct CleanupEvidence<'a> {
    format_version: u32,
    candidate_sha: &'a str,
    scope: &'static str,
    cleanup_result: &'static str,
    provider_delete_dispatched: bool,
    provider_deletion_confirmed: bool,
    durable_terminal_confirmed: bool,
    provider_identifier_recorded: bool,
    transport_endpoint_recorded: bool,
    secret_values_recorded: bool,
    final_production_authority: bool,
    production_environment_authorized: bool,
    phone_mutation_performed: bool,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        LifecycleCommand::PrepareArtifact {
            candidate_sha,
            root,
            manifest,
        } => prepare_artifact(&candidate_sha, &root, &manifest),
        LifecycleCommand::VerifyArtifact {
            candidate_sha,
            root,
            manifest,
        } => verify_artifact(&candidate_sha, &root, &manifest),
        LifecycleCommand::ReconcileDeploy {
            candidate_sha,
            admission_evidence,
            artifact_root,
            manifest,
            ssh_private_key,
            evidence_output,
        } => reconcile_deploy(
            &candidate_sha,
            &admission_evidence,
            &artifact_root,
            &manifest,
            &ssh_private_key,
            &evidence_output,
        ),
        LifecycleCommand::Cleanup {
            candidate_sha,
            evidence_output,
        } => cleanup(&candidate_sha, &evidence_output),
    }
}

fn validate_candidate_sha(candidate_sha: &str) -> Result<()> {
    if candidate_sha.len() != 40
        || !candidate_sha
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        bail!("candidate SHA must be an exact lowercase 40-character hexadecimal commit identity");
    }
    Ok(())
}

fn validate_manifest_location(root: &Path, manifest: &Path) -> Result<()> {
    if manifest != root.join(MANIFEST_NAME) {
        bail!("item 19 artifact manifest must be the fixed manifest.json inside artifact root");
    }
    Ok(())
}

fn artifact_entries(root: &Path) -> Result<Vec<ArtifactEntry>> {
    let mut files = Vec::new();
    collect_artifact_files(root, root, &mut files)?;
    files.sort();
    let manifest_relative = MANIFEST_NAME.to_owned();
    let actual: BTreeSet<_> = files
        .iter()
        .filter(|path| **path != manifest_relative)
        .cloned()
        .collect();
    let required: BTreeSet<_> = REQUIRED_ARTIFACT_FILES
        .iter()
        .map(|path| (*path).to_owned())
        .collect();
    if actual != required {
        bail!("item 19 server artifact contains missing or unexpected files");
    }

    let mut entries = Vec::with_capacity(REQUIRED_ARTIFACT_FILES.len());
    for relative in REQUIRED_ARTIFACT_FILES {
        let path = root.join(relative);
        let metadata = fs::symlink_metadata(&path)
            .with_context(|| format!("required artifact file is missing: {relative}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            bail!("item 19 artifact entries must be regular files");
        }
        if metadata.len() == 0 || metadata.len() > MAX_ARTIFACT_FILE_BYTES {
            bail!("item 19 artifact entry size is invalid");
        }
        let bytes = fs::read(&path).context("cannot read bounded item 19 artifact file")?;
        let digest = ContentDigest::derive(ARTIFACT_DIGEST_DOMAIN, [bytes.as_slice()]);
        entries.push(ArtifactEntry {
            path: relative.to_owned(),
            size_bytes: metadata.len(),
            digest,
        });
    }
    Ok(entries)
}

fn collect_artifact_files(root: &Path, directory: &Path, files: &mut Vec<String>) -> Result<()> {
    for entry in fs::read_dir(directory).context("cannot enumerate item 19 artifact")? {
        let entry = entry.context("cannot enumerate item 19 artifact entry")?;
        let path = entry.path();
        let metadata =
            fs::symlink_metadata(&path).context("cannot inspect item 19 artifact entry")?;
        if metadata.file_type().is_symlink() {
            bail!("item 19 artifact must not contain symlinks");
        }
        if metadata.is_dir() {
            collect_artifact_files(root, &path, files)?;
            continue;
        }
        if !metadata.is_file() {
            bail!("item 19 artifact contains an unsupported filesystem entry");
        }
        let relative = path
            .strip_prefix(root)
            .context("artifact entry escaped artifact root")?
            .to_str()
            .context("artifact path is not UTF-8")?
            .replace('\\', "/");
        files.push(relative);
    }
    Ok(())
}

fn prepare_artifact(candidate_sha: &str, root: &Path, manifest: &Path) -> Result<()> {
    validate_candidate_sha(candidate_sha)?;
    validate_manifest_location(root, manifest)?;
    let metadata = fs::symlink_metadata(root).context("item 19 artifact root is missing")?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        bail!("item 19 artifact root must be a real directory");
    }
    let artifact = ArtifactManifest {
        format_version: MANIFEST_FORMAT_VERSION,
        candidate_sha: candidate_sha.to_owned(),
        digest_domain: ARTIFACT_DIGEST_DOMAIN.as_str().to_owned(),
        files: artifact_entries(root)?,
    };
    fs::write(manifest, serde_json::to_vec_pretty(&artifact)?)
        .context("cannot write item 19 artifact manifest")?;
    verify_artifact(candidate_sha, root, manifest)
}

fn verify_artifact(candidate_sha: &str, root: &Path, manifest: &Path) -> Result<()> {
    validate_candidate_sha(candidate_sha)?;
    validate_manifest_location(root, manifest)?;
    let metadata =
        fs::symlink_metadata(manifest).context("item 19 artifact manifest is missing")?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        bail!("item 19 artifact manifest must be a regular file");
    }
    if metadata.len() == 0 || metadata.len() > MAX_JSON_BYTES {
        bail!("item 19 artifact manifest size is invalid");
    }
    let artifact: ArtifactManifest = serde_json::from_slice(&fs::read(manifest)?)
        .context("invalid item 19 artifact manifest")?;
    if artifact.format_version != MANIFEST_FORMAT_VERSION
        || artifact.candidate_sha != candidate_sha
        || artifact.digest_domain != ARTIFACT_DIGEST_DOMAIN.as_str()
    {
        bail!("item 19 artifact manifest identity does not match exact candidate");
    }
    let expected = artifact_entries(root)?;
    if artifact.files != expected {
        bail!("item 19 artifact bytes do not match immutable manifest");
    }
    Ok(())
}

fn read_bounded_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T> {
    let metadata = fs::metadata(path).context("required JSON evidence is missing")?;
    if metadata.len() == 0 || metadata.len() > MAX_JSON_BYTES {
        bail!("JSON evidence size is invalid");
    }
    serde_json::from_slice(&fs::read(path)?).context("JSON evidence is invalid")
}

fn positive_numeric(value: &str) -> bool {
    !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()) && value != "0"
}

fn verify_admission_evidence(candidate_sha: &str, path: &Path) -> Result<()> {
    let evidence: AdmissionEvidence = read_bounded_json(path)?;
    let numeric_identities = [
        &evidence.workflow_run_id,
        &evidence.workflow_run_attempt,
        &evidence.command_comment_id,
        &evidence.quality_run_id,
        &evidence.quality_run_attempt,
        &evidence.acceptance_run_id,
        &evidence.acceptance_run_attempt,
        &evidence.preflight_run_id,
        &evidence.preflight_run_attempt,
    ];
    if evidence.format_version != 1
        || evidence.authority != ADMISSION_AUTHORITY
        || evidence.candidate_sha != candidate_sha
        || evidence.repository != CANONICAL_REPOSITORY
        || evidence.command_issue != ITEM19_ISSUE
        || evidence.signing_continuity_gate_issue != SIGNING_GATE_ISSUE
        || !evidence.physical_acceptance_window_ready
        || !evidence.signing_continuity_gate_closed
        || evidence.scope != LifecycleScope::Acceptance.as_str()
        || evidence.environment != ACCEPTANCE_ENVIRONMENT
        || evidence.final_production_authority
        || evidence.production_environment_authorized
        || evidence.phone_mutation_authorized
        || evidence.provider_mutation_performed_at_admission
        || numeric_identities
            .into_iter()
            .any(|value| !positive_numeric(value))
    {
        bail!("item 19 admission evidence does not authorize bounded acceptance lifecycle");
    }
    Ok(())
}

fn required_env(name: &str) -> Result<String> {
    let value =
        env::var(name).map_err(|_| anyhow::anyhow!("required workflow credential is absent"))?;
    if value.is_empty() {
        bail!("required workflow credential is absent");
    }
    Ok(value)
}

fn acceptance_spec() -> VultrVmSpec {
    VultrVmSpec {
        region: ACCEPTANCE_REGION.to_owned(),
        plan: ACCEPTANCE_PLAN.to_owned(),
        os_id: ACCEPTANCE_OS_ID,
        label: ACCEPTANCE_LABEL.to_owned(),
    }
}

fn acceptance_desired(candidate_sha: &str) -> Result<DesiredVm> {
    let spec = acceptance_spec();
    Ok(DesiredVm {
        intent: OwnershipIntent::new(
            LifecycleScope::Acceptance,
            format!("candidate:{candidate_sha}"),
        )?,
        display_name: spec.label.clone(),
        spec_fingerprint: spec.fingerprint(),
    })
}

fn derive_public_key(private_key: &Path) -> Result<String> {
    let metadata = fs::metadata(private_key).context("SSH private key is unavailable")?;
    if !metadata.is_file() || metadata.len() == 0 {
        bail!("SSH private key is unavailable");
    }
    let output = Command::new("ssh-keygen")
        .arg("-y")
        .arg("-f")
        .arg(private_key)
        .output()
        .context("cannot derive SSH public key")?;
    if !output.status.success() {
        bail!("cannot derive SSH public key");
    }
    let key = std::str::from_utf8(&output.stdout)
        .context("derived SSH public key is invalid")?
        .trim();
    if key.is_empty()
        || key.len() > MAX_PUBLIC_KEY_BYTES
        || key.contains('\n')
        || !matches!(
            key.split_whitespace().next(),
            Some(
                "ssh-ed25519"
                    | "ssh-rsa"
                    | "ecdsa-sha2-nistp256"
                    | "ecdsa-sha2-nistp384"
                    | "ecdsa-sha2-nistp521"
            )
        )
    {
        bail!("derived SSH public key is invalid");
    }
    Ok(key.to_owned())
}

fn build_cloud_init(public_key: &str) -> String {
    format!(
        "#cloud-config\ndisable_root: false\nssh_pwauth: false\nusers:\n  - default\n  - name: root\n    lock_passwd: true\n    ssh_authorized_keys:\n      - {public_key}\n"
    )
}

fn recover_create_binding(
    store: &mut DurableGitHubVmBindingStore,
    client: &VultrAcceptanceClient,
    desired: &DesiredVm,
    generation: Generation,
) -> Result<VmBinding> {
    let fence = create_dispatch_fence_for_recovery(&desired.intent, generation, desired)?;
    for _ in 0..PROVIDER_RECOVERY_ATTEMPTS {
        let observed = client.list_instances()?;
        match recover_dispatched_create(&fence, &observed)? {
            CreateRecovery::AwaitProvider => thread::sleep(PROVIDER_RECOVERY_DELAY),
            CreateRecovery::Recovered(recovered) => {
                let binding = recovered.binding().clone();
                store.compare_and_swap(&desired.intent, None, Some(binding.clone()))?;
                return Ok(binding);
            }
        }
    }
    bail!("dispatched acceptance VM create did not converge within bounded recovery window")
}

fn dispatch_create(
    store: &mut DurableGitHubVmBindingStore,
    client: &VultrAcceptanceClient,
    desired: &DesiredVm,
    user_data_b64: &str,
    prepared_generation: Option<Generation>,
) -> Result<VmBinding> {
    let observed = client.list_instances()?;
    let ReconcilePlan::Create(plan) = plan_present(None, &observed, desired, None)? else {
        bail!("unbound acceptance intent is not eligible for exactly one create");
    };
    let fence = create_dispatch_fence(&plan, desired)?;
    let generation = match prepared_generation {
        Some(generation) => generation,
        None => store.prepare_create(&desired.intent)?,
    };
    if generation != fence.generation() {
        bail!("durable create generation does not match provider-neutral create plan");
    }
    store.mark_create_dispatched(&desired.intent, generation)?;

    let create_result =
        client.create_instance_with_user_data(&plan, &acceptance_spec(), user_data_b64);
    if create_result.is_err() {
        bail!(
            "acceptance VM create dispatch outcome is ambiguous; retry exact candidate for durable recovery"
        );
    }
    recover_create_binding(store, client, desired, generation)
}

fn ensure_bound(
    store: &mut DurableGitHubVmBindingStore,
    client: &VultrAcceptanceClient,
    desired: &DesiredVm,
    user_data_b64: &str,
) -> Result<(VmBinding, BindOrigin)> {
    match store.lifecycle_state(&desired.intent)? {
        AcceptanceVmLifecycleState::Empty => Ok((
            dispatch_create(store, client, desired, user_data_b64, None)?,
            BindOrigin::Created,
        )),
        AcceptanceVmLifecycleState::CreatePrepared { generation } => Ok((
            dispatch_create(store, client, desired, user_data_b64, Some(generation))?,
            BindOrigin::Created,
        )),
        AcceptanceVmLifecycleState::CreateDispatched { generation } => Ok((
            recover_create_binding(store, client, desired, generation)?,
            BindOrigin::Recovered,
        )),
        AcceptanceVmLifecycleState::Bound(binding) => {
            let observed = client.list_instances()?;
            match plan_present(Some(&binding), &observed, desired, Some(binding.generation))? {
                ReconcilePlan::Noop(_) => Ok((binding, BindOrigin::Existing)),
                ReconcilePlan::Reconfigure(_) => {
                    bail!(
                        "bound acceptance VM specification drifted; item 19 will not reconfigure it"
                    )
                }
                ReconcilePlan::Create(_) => {
                    bail!("bound acceptance state unexpectedly planned another create")
                }
            }
        }
        AcceptanceVmLifecycleState::DeletePrepared(_)
        | AcceptanceVmLifecycleState::DeleteDispatched(_) => {
            bail!("acceptance VM cleanup is already in progress")
        }
        AcceptanceVmLifecycleState::Terminal { .. } => {
            bail!("terminal acceptance intent cannot be reused")
        }
    }
}

fn verified_bound_target(
    client: &VultrAcceptanceClient,
    desired: &DesiredVm,
    binding: &VmBinding,
) -> Result<VerifiedMutationTarget> {
    let observed = client.list_instances()?;
    match plan_present(Some(binding), &observed, desired, Some(binding.generation))? {
        ReconcilePlan::Noop(target) => Ok(target),
        ReconcilePlan::Reconfigure(_) => {
            bail!("acceptance VM specification drifted before transport resolution")
        }
        ReconcilePlan::Create(_) => bail!("bound acceptance VM unexpectedly resolved as create"),
    }
}

fn ssh_base_args(private_key: &Path, known_hosts: &Path) -> Vec<String> {
    vec![
        "-i".to_owned(),
        private_key.display().to_string(),
        "-o".to_owned(),
        "BatchMode=yes".to_owned(),
        "-o".to_owned(),
        "IdentitiesOnly=yes".to_owned(),
        "-o".to_owned(),
        "ConnectTimeout=5".to_owned(),
        "-o".to_owned(),
        "ConnectionAttempts=1".to_owned(),
        "-o".to_owned(),
        "StrictHostKeyChecking=accept-new".to_owned(),
        "-o".to_owned(),
        format!("UserKnownHostsFile={}", known_hosts.display()),
        "-o".to_owned(),
        "LogLevel=ERROR".to_owned(),
    ]
}

fn ssh_command_ok(
    address: Ipv4Addr,
    private_key: &Path,
    known_hosts: &Path,
    remote_command: &str,
) -> Result<bool> {
    let mut command = Command::new("ssh");
    command.args(ssh_base_args(private_key, known_hosts));
    command.arg(format!("root@{address}"));
    command.arg(remote_command);
    let output = command
        .output()
        .context("cannot execute automated SSH transport")?;
    Ok(output.status.success())
}

fn wait_for_ssh(
    client: &VultrAcceptanceClient,
    target: &VerifiedMutationTarget,
    private_key: &Path,
    known_hosts: &Path,
) -> Result<Ipv4Addr> {
    for _ in 0..SSH_READY_ATTEMPTS {
        match client.instance_ipv4(target) {
            Ok(address) => {
                if ssh_command_ok(address, private_key, known_hosts, "true")? {
                    return Ok(address);
                }
            }
            Err(VultrClientError::InvalidTransportEndpoint)
            | Err(VultrClientError::Transport)
            | Err(VultrClientError::HttpStatus(
                404 | 408 | 409 | 425 | 429 | 500 | 502 | 503 | 504,
            )) => {}
            Err(error) => return Err(error.into()),
        }
        thread::sleep(SSH_READY_DELAY);
    }
    bail!("verified acceptance VM did not become SSH-ready within bounded window")
}

fn scp_file(
    address: Ipv4Addr,
    private_key: &Path,
    known_hosts: &Path,
    local: &Path,
    remote: &str,
) -> Result<()> {
    let mut command = Command::new("scp");
    command.args(ssh_base_args(private_key, known_hosts));
    command.arg(local);
    command.arg(format!("root@{address}:{remote}"));
    let output = command
        .output()
        .context("cannot execute automated SCP transport")?;
    if !output.status.success() {
        bail!("automated artifact transfer failed");
    }
    Ok(())
}

fn deploy_and_verify_artifact(
    candidate_sha: &str,
    artifact_root: &Path,
    private_key: &Path,
    address: Ipv4Addr,
    known_hosts: &Path,
) -> Result<()> {
    let remote_root = format!("{REMOTE_ROOT_PREFIX}/{candidate_sha}");
    let remote_bin = format!("{remote_root}/bin");
    let create_dirs = format!("install -d -m 0755 {remote_root} {remote_bin}");
    if !ssh_command_ok(address, private_key, known_hosts, &create_dirs)? {
        bail!("cannot prepare exact acceptance artifact directory");
    }

    scp_file(
        address,
        private_key,
        known_hosts,
        &artifact_root.join(MANIFEST_NAME),
        &format!("{remote_root}/{MANIFEST_NAME}"),
    )?;
    for relative in REQUIRED_ARTIFACT_FILES {
        scp_file(
            address,
            private_key,
            known_hosts,
            &artifact_root.join(relative),
            &format!("{remote_root}/{relative}"),
        )?;
    }

    let verify_command = format!(
        "chmod 0755 {remote_bin}/control-plane {remote_bin}/relay-gate {remote_bin}/reverse-tunnel-server {remote_bin}/item19-acceptance-lifecycle && {remote_bin}/item19-acceptance-lifecycle verify-artifact --candidate-sha {candidate_sha} --root {remote_root} --manifest {remote_root}/{MANIFEST_NAME}"
    );
    if !ssh_command_ok(address, private_key, known_hosts, &verify_command)? {
        bail!("deployed exact-candidate artifact verification failed");
    }
    Ok(())
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    fs::write(path, serde_json::to_vec_pretty(value)?)
        .context("cannot write bounded item 19 evidence")
}

fn reconcile_deploy(
    candidate_sha: &str,
    admission_evidence: &Path,
    artifact_root: &Path,
    manifest: &Path,
    ssh_private_key: &Path,
    evidence_output: &Path,
) -> Result<()> {
    validate_candidate_sha(candidate_sha)?;
    verify_admission_evidence(candidate_sha, admission_evidence)?;
    verify_artifact(candidate_sha, artifact_root, manifest)?;

    let public_key = derive_public_key(ssh_private_key)?;
    let cloud_init = build_cloud_init(&public_key);
    let user_data_b64 = STANDARD.encode(cloud_init.as_bytes());
    let desired = acceptance_desired(candidate_sha)?;
    let mut store =
        DurableGitHubVmBindingStore::new(required_env("GITHUB_TOKEN")?, candidate_sha.to_owned())?;
    let client = VultrAcceptanceClient::new(required_env("VULTR_API_KEY")?)?;
    let (binding, origin) = ensure_bound(&mut store, &client, &desired, &user_data_b64)?;
    let target = verified_bound_target(&client, &desired, &binding)?;
    let known_hosts = ssh_private_key.with_extension("known_hosts");
    let _ = fs::remove_file(&known_hosts);
    let address = wait_for_ssh(&client, &target, ssh_private_key, &known_hosts)?;
    deploy_and_verify_artifact(
        candidate_sha,
        artifact_root,
        ssh_private_key,
        address,
        &known_hosts,
    )?;

    write_json(
        evidence_output,
        &DeployEvidence {
            format_version: 1,
            candidate_sha,
            scope: LifecycleScope::Acceptance.as_str(),
            lifecycle_result: "bound_and_exact_candidate_deployed",
            binding_origin: origin.as_str(),
            generation: binding.generation.get(),
            artifact_verified_before_transport: true,
            deployed_artifact_verified_on_target: true,
            transport_endpoint_recorded: false,
            provider_identifier_recorded: false,
            secret_values_recorded: false,
            final_production_authority: false,
            production_environment_authorized: false,
            phone_mutation_performed: false,
        },
    )
}

fn resolve_delete_target(
    client: &VultrAcceptanceClient,
    binding: &VmBinding,
) -> Result<VerifiedMutationTarget> {
    let observed = client.list_instances()?;
    authorize_mutation(binding, &observed, binding.generation, MutationKind::Delete)
        .map_err(Into::into)
}

fn confirm_provider_deleted(client: &VultrAcceptanceClient, binding: &VmBinding) -> Result<()> {
    for _ in 0..DELETE_CONFIRM_ATTEMPTS {
        let observed = client.list_instances()?;
        match authorize_mutation(binding, &observed, binding.generation, MutationKind::Delete) {
            Err(LifecycleError::ProviderResourceNotFound) => return Ok(()),
            Ok(_) => thread::sleep(DELETE_CONFIRM_DELAY),
            Err(error) => return Err(error.into()),
        }
    }
    bail!("exact acceptance VM deletion was not confirmed within bounded window")
}

fn terminal_matches(store: &DurableGitHubVmBindingStore, binding: &VmBinding) -> Result<bool> {
    Ok(matches!(
        store.lifecycle_state(&binding.intent)?,
        AcceptanceVmLifecycleState::Terminal { last_generation }
            if last_generation == binding.generation
    ))
}

fn delete_bound(
    store: &mut DurableGitHubVmBindingStore,
    client: &VultrAcceptanceClient,
    binding: &VmBinding,
    already_prepared: bool,
    already_dispatched: bool,
) -> Result<()> {
    let target = resolve_delete_target(client, binding)?;
    if !already_prepared {
        store.prepare_delete(&binding.intent, binding)?;
    }
    if !already_dispatched {
        store.mark_delete_dispatched(&binding.intent, binding)?;
    }
    client.delete_instance(&target)?;
    confirm_provider_deleted(client, binding)?;
    store.compare_and_swap(&binding.intent, Some(binding), None)?;
    if !terminal_matches(store, binding)? {
        bail!("durable acceptance lifecycle did not reach terminal after confirmed delete");
    }
    Ok(())
}

fn recover_dispatched_delete(
    store: &mut DurableGitHubVmBindingStore,
    client: &VultrAcceptanceClient,
    binding: &VmBinding,
) -> Result<()> {
    let observed = client.list_instances()?;
    match authorize_mutation(binding, &observed, binding.generation, MutationKind::Delete) {
        Err(LifecycleError::ProviderResourceNotFound) => {
            store.compare_and_swap(&binding.intent, Some(binding), None)?;
        }
        Ok(target) => {
            client.delete_instance(&target)?;
            confirm_provider_deleted(client, binding)?;
            store.compare_and_swap(&binding.intent, Some(binding), None)?;
        }
        Err(error) => return Err(error.into()),
    }
    if !terminal_matches(store, binding)? {
        bail!("durable acceptance lifecycle did not reach terminal during delete recovery");
    }
    Ok(())
}

fn cleanup(candidate_sha: &str, evidence_output: &Path) -> Result<()> {
    validate_candidate_sha(candidate_sha)?;
    let desired = acceptance_desired(candidate_sha)?;
    let mut store =
        DurableGitHubVmBindingStore::new(required_env("GITHUB_TOKEN")?, candidate_sha.to_owned())?;
    let client = VultrAcceptanceClient::new(required_env("VULTR_API_KEY")?)?;
    let mut delete_dispatched = false;
    let mut deletion_confirmed = false;
    let mut terminal = false;

    match store.lifecycle_state(&desired.intent)? {
        AcceptanceVmLifecycleState::Empty => {}
        AcceptanceVmLifecycleState::CreatePrepared { .. } => {
            bail!(
                "create was prepared but never dispatch-fenced; retry exact candidate before cleanup"
            )
        }
        AcceptanceVmLifecycleState::CreateDispatched { generation } => {
            let binding = recover_create_binding(&mut store, &client, &desired, generation)?;
            delete_bound(&mut store, &client, &binding, false, false)?;
            delete_dispatched = true;
            deletion_confirmed = true;
            terminal = true;
        }
        AcceptanceVmLifecycleState::Bound(binding) => {
            delete_bound(&mut store, &client, &binding, false, false)?;
            delete_dispatched = true;
            deletion_confirmed = true;
            terminal = true;
        }
        AcceptanceVmLifecycleState::DeletePrepared(binding) => {
            delete_bound(&mut store, &client, &binding, true, false)?;
            delete_dispatched = true;
            deletion_confirmed = true;
            terminal = true;
        }
        AcceptanceVmLifecycleState::DeleteDispatched(binding) => {
            recover_dispatched_delete(&mut store, &client, &binding)?;
            delete_dispatched = true;
            deletion_confirmed = true;
            terminal = true;
        }
        AcceptanceVmLifecycleState::Terminal { .. } => {
            delete_dispatched = true;
            deletion_confirmed = true;
            terminal = true;
        }
    }

    write_json(
        evidence_output,
        &CleanupEvidence {
            format_version: 1,
            candidate_sha,
            scope: LifecycleScope::Acceptance.as_str(),
            cleanup_result: if terminal {
                "terminal"
            } else {
                "no_provider_resource_created"
            },
            provider_delete_dispatched: delete_dispatched,
            provider_deletion_confirmed: deletion_confirmed,
            durable_terminal_confirmed: terminal,
            provider_identifier_recorded: false,
            transport_endpoint_recorded: false,
            secret_values_recorded: false,
            final_production_authority: false,
            production_environment_authorized: false,
            phone_mutation_performed: false,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root(name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = env::temp_dir().join(format!("mobile-proxy-{name}-{nonce}"));
        fs::create_dir_all(root.join("bin")).unwrap();
        root
    }

    fn create_artifact(root: &Path) {
        for relative in REQUIRED_ARTIFACT_FILES {
            let path = root.join(relative);
            fs::write(&path, format!("bytes:{relative}")).unwrap();
            let mut permissions = fs::metadata(&path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(path, permissions).unwrap();
        }
    }

    #[test]
    fn exact_candidate_sha_rejects_abbreviations_and_uppercase() {
        assert!(validate_candidate_sha(&"a".repeat(40)).is_ok());
        assert!(validate_candidate_sha(&"a".repeat(12)).is_err());
        assert!(validate_candidate_sha(&"A".repeat(40)).is_err());
    }

    #[test]
    fn artifact_manifest_binds_exact_candidate_and_bytes() {
        let root = temp_root("artifact");
        create_artifact(&root);
        let manifest = root.join(MANIFEST_NAME);
        let sha = "a".repeat(40);
        prepare_artifact(&sha, &root, &manifest).unwrap();
        verify_artifact(&sha, &root, &manifest).unwrap();
        fs::write(root.join("bin/control-plane"), b"tampered").unwrap();
        assert!(verify_artifact(&sha, &root, &manifest).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn artifact_rejects_extra_files() {
        let root = temp_root("extra-artifact");
        create_artifact(&root);
        fs::write(root.join("unexpected"), b"nope").unwrap();
        let sha = "a".repeat(40);
        assert!(prepare_artifact(&sha, &root, &root.join(MANIFEST_NAME)).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn cloud_init_contains_only_public_transport_material() {
        let public = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest";
        let cloud_init = build_cloud_init(public);
        assert!(cloud_init.starts_with("#cloud-config\n"));
        assert!(cloud_init.contains("disable_root: false"));
        assert!(cloud_init.contains(public));
        assert!(!cloud_init.contains("PRIVATE KEY"));
        assert!(!cloud_init.contains("VULTR_API_KEY"));
    }

    #[test]
    fn fixed_acceptance_spec_is_not_production_configurable() {
        let spec = acceptance_spec();
        assert_eq!(spec.region, "waw");
        assert_eq!(spec.plan, "vc2-1c-2gb");
        assert_eq!(spec.os_id, 2284);
        assert_eq!(spec.label, "mobile-proxy-acceptance");
        let desired = acceptance_desired(&"a".repeat(40)).unwrap();
        assert_eq!(desired.intent.scope(), LifecycleScope::Acceptance);
    }
}
