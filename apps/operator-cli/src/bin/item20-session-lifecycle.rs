use anyhow::{Context, Result, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use clap::{Parser, Subcommand};
use operator_cli::github_vm_binding_store::{
    AcceptanceVmLifecycleState, DurableGitHubVmBindingStore,
};
use operator_cli::item20_acceptance::Item20SessionIdentity;
use operator_cli::item20_session_lifecycle::{
    SessionCloseOutcome, SessionOpenOrigin, close_item20_session, open_item20_session,
    verified_item20_target,
};
use operator_cli::vultr_client::VultrAcceptanceClient;
use serde::Serialize;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const CANONICAL_REPOSITORY: &str = "iamaman11/mobile-proxy";
const CANONICAL_REF: &str = "refs/heads/main";
const MAX_PUBLIC_KEY_BYTES: u64 = 16 * 1024;

#[derive(Parser)]
#[command(name = "item20-session-lifecycle")]
struct Cli {
    #[command(subcommand)]
    command: LifecycleCommand,
}

#[derive(Subcommand)]
enum LifecycleCommand {
    Open {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        control_plane_sha: String,
        #[arg(long)]
        ssh_public_key: PathBuf,
        #[arg(long)]
        evidence_output: PathBuf,
    },
    VerifyTarget {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        control_plane_sha: String,
        #[arg(long)]
        evidence_output: PathBuf,
    },
    Close {
        #[arg(long)]
        candidate_sha: String,
        #[arg(long)]
        control_plane_sha: String,
        #[arg(long)]
        evidence_output: PathBuf,
    },
}

#[derive(Serialize)]
struct LifecycleEvidence<'a> {
    format_version: u32,
    candidate_sha: &'a str,
    control_plane_sha: &'a str,
    action: &'static str,
    result: &'static str,
    generation: Option<u64>,
    exact_target_verified: bool,
    provider_identifier_recorded: bool,
    transport_endpoint_recorded: bool,
    secret_values_recorded: bool,
    endpoint_handoff_authorized: bool,
    phone_mutation_performed: bool,
    final_production_authority: bool,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        LifecycleCommand::Open {
            candidate_sha,
            control_plane_sha,
            ssh_public_key,
            evidence_output,
        } => open(
            &candidate_sha,
            &control_plane_sha,
            &ssh_public_key,
            &evidence_output,
        ),
        LifecycleCommand::VerifyTarget {
            candidate_sha,
            control_plane_sha,
            evidence_output,
        } => verify_target(&candidate_sha, &control_plane_sha, &evidence_output),
        LifecycleCommand::Close {
            candidate_sha,
            control_plane_sha,
            evidence_output,
        } => close(&candidate_sha, &control_plane_sha, &evidence_output),
    }
}

fn verified_identity(
    candidate_sha: &str,
    control_plane_sha: &str,
) -> Result<Item20SessionIdentity> {
    verify_canonical_runtime(control_plane_sha)?;
    Item20SessionIdentity::new(candidate_sha, control_plane_sha)
}

fn verify_canonical_runtime(control_plane_sha: &str) -> Result<()> {
    let repository = env::var("GITHUB_REPOSITORY").unwrap_or_default();
    let git_ref = env::var("GITHUB_REF").unwrap_or_default();
    let protected = env::var("GITHUB_REF_PROTECTED").unwrap_or_default();
    let github_sha = env::var("GITHUB_SHA").unwrap_or_default();
    if repository != CANONICAL_REPOSITORY
        || git_ref != CANONICAL_REF
        || protected != "true"
        || github_sha != control_plane_sha
    {
        bail!("Item 20 lifecycle entrypoint requires the exact protected canonical main runtime");
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

fn read_public_key(path: &Path) -> Result<String> {
    let metadata = fs::symlink_metadata(path).context("SSH public key is unavailable")?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() == 0
        || metadata.len() > MAX_PUBLIC_KEY_BYTES
    {
        bail!("SSH public key is unavailable");
    }
    let raw = fs::read_to_string(path).context("SSH public key is invalid")?;
    parse_public_key_line(&raw)
}

fn parse_public_key_line(raw: &str) -> Result<String> {
    let key = raw.trim();
    if key.is_empty() || key.contains('\n') || key.contains('\r') {
        bail!("SSH public key is invalid");
    }
    let mut fields = key.split_ascii_whitespace();
    let Some(kind) = fields.next() else {
        bail!("SSH public key is invalid");
    };
    let Some(body) = fields.next() else {
        bail!("SSH public key is invalid");
    };
    if fields.next().is_some()
        || !matches!(
            kind,
            "ssh-ed25519"
                | "ssh-rsa"
                | "ecdsa-sha2-nistp256"
                | "ecdsa-sha2-nistp384"
                | "ecdsa-sha2-nistp521"
        )
        || body.is_empty()
        || !body
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/' | b'='))
    {
        bail!("SSH public key is invalid");
    }
    Ok(format!("{kind} {body}"))
}

fn build_cloud_init(public_key: &str) -> String {
    format!(
        "#cloud-config\ndisable_root: false\nssh_pwauth: false\nusers:\n  - default\n  - name: root\n    lock_passwd: true\n    ssh_authorized_keys:\n      - {public_key}\n"
    )
}

fn store_and_provider(
    candidate_sha: &str,
) -> Result<(DurableGitHubVmBindingStore, VultrAcceptanceClient)> {
    let store = DurableGitHubVmBindingStore::new_item20(
        required_env("GITHUB_TOKEN")?,
        candidate_sha.to_owned(),
    )?;
    let provider = VultrAcceptanceClient::new(required_env("VULTR_API_KEY")?)?;
    Ok((store, provider))
}

fn write_evidence(path: &Path, evidence: &LifecycleEvidence<'_>) -> Result<()> {
    fs::write(path, serde_json::to_vec_pretty(evidence)?)
        .context("cannot write bounded Item 20 lifecycle evidence")
}

fn open(
    candidate_sha: &str,
    control_plane_sha: &str,
    ssh_public_key: &Path,
    evidence_output: &Path,
) -> Result<()> {
    let identity = verified_identity(candidate_sha, control_plane_sha)?;
    let public_key = read_public_key(ssh_public_key)?;
    let user_data_b64 = STANDARD.encode(build_cloud_init(&public_key).as_bytes());
    let (mut store, provider) = store_and_provider(candidate_sha)?;
    let opened = open_item20_session(&mut store, &provider, &identity, &user_data_b64)?;
    let _target = verified_item20_target(&provider, &identity, &opened.binding)?;
    let result = match opened.origin {
        SessionOpenOrigin::Existing => "existing",
        SessionOpenOrigin::Created => "created",
        SessionOpenOrigin::Recovered => "recovered",
    };
    write_evidence(
        evidence_output,
        &LifecycleEvidence {
            format_version: 1,
            candidate_sha,
            control_plane_sha,
            action: "open",
            result,
            generation: Some(opened.binding.generation.get()),
            exact_target_verified: true,
            provider_identifier_recorded: false,
            transport_endpoint_recorded: false,
            secret_values_recorded: false,
            endpoint_handoff_authorized: false,
            phone_mutation_performed: false,
            final_production_authority: false,
        },
    )
}

fn verify_target(
    candidate_sha: &str,
    control_plane_sha: &str,
    evidence_output: &Path,
) -> Result<()> {
    let identity = verified_identity(candidate_sha, control_plane_sha)?;
    let (store, provider) = store_and_provider(candidate_sha)?;
    let intent = identity.ownership_intent()?;
    let binding = match store.lifecycle_state(&intent)? {
        AcceptanceVmLifecycleState::Bound(binding) => binding,
        _ => bail!(
            "Item 20 lifecycle is not in the exact bound state required for target verification"
        ),
    };
    let _target = verified_item20_target(&provider, &identity, &binding)?;
    write_evidence(
        evidence_output,
        &LifecycleEvidence {
            format_version: 1,
            candidate_sha,
            control_plane_sha,
            action: "verify-target",
            result: "exact_bound_target_verified",
            generation: Some(binding.generation.get()),
            exact_target_verified: true,
            provider_identifier_recorded: false,
            transport_endpoint_recorded: false,
            secret_values_recorded: false,
            endpoint_handoff_authorized: false,
            phone_mutation_performed: false,
            final_production_authority: false,
        },
    )
}

fn close(candidate_sha: &str, control_plane_sha: &str, evidence_output: &Path) -> Result<()> {
    let identity = verified_identity(candidate_sha, control_plane_sha)?;
    let (mut store, provider) = store_and_provider(candidate_sha)?;
    let outcome = close_item20_session(&mut store, &provider, &identity)?;
    let result = match outcome {
        SessionCloseOutcome::NoResourceCreated => "no_resource_created",
        SessionCloseOutcome::DeletedAndTerminal => "deleted_and_terminal",
        SessionCloseOutcome::AlreadyTerminal => "already_terminal",
    };
    write_evidence(
        evidence_output,
        &LifecycleEvidence {
            format_version: 1,
            candidate_sha,
            control_plane_sha,
            action: "close",
            result,
            generation: None,
            exact_target_verified: false,
            provider_identifier_recorded: false,
            transport_endpoint_recorded: false,
            secret_values_recorded: false,
            endpoint_handoff_authorized: false,
            phone_mutation_performed: false,
            final_production_authority: false,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_key_parser_accepts_only_bounded_two_field_keys() {
        assert_eq!(
            parse_public_key_line("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA==\n").unwrap(),
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA=="
        );
        for invalid in [
            "",
            "ssh-ed25519",
            "ssh-ed25519 AAAA comment",
            "ssh-ed25519 AAAA;rm",
            "unknown AAAA",
            "ssh-ed25519 AAAA\nssh-rsa BBBB",
        ] {
            assert!(parse_public_key_line(invalid).is_err());
        }
    }

    #[test]
    fn cloud_init_contains_only_the_validated_public_key() {
        let key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA==";
        let cloud_init = build_cloud_init(key);
        assert!(cloud_init.contains(key));
        assert!(cloud_init.contains("ssh_pwauth: false"));
        assert!(!cloud_init.contains("VULTR_API_KEY"));
    }
}
