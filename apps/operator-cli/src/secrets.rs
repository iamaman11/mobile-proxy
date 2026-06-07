use std::fs::{self, OpenOptions};
use std::io::Write;
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

use anyhow::{Context, Result, bail};
use base64::Engine;

use crate::cli::GenerateReverseTunnelIdentityArgs;

pub fn generate_reverse_tunnel_identity(args: &GenerateReverseTunnelIdentityArgs) -> Result<()> {
    let output = Path::new(&args.output_env_file);
    if output.exists() && !args.overwrite {
        bail!(
            "{} already exists; pass --overwrite to replace it",
            output.display()
        );
    }
    if let Some(parent) = output.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    let certified = rcgen::generate_simple_self_signed(vec![args.server_name.clone()])
        .context("failed to generate reverse tunnel certificate")?;
    let cert_b64 = base64::engine::general_purpose::STANDARD.encode(certified.cert.der().as_ref());
    let key_b64 =
        base64::engine::general_purpose::STANDARD.encode(certified.signing_key.serialize_der());
    let body = format!(
        "MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64='{}'\nMOBILE_PROXY_REVERSE_TUNNEL_KEY_DER_B64='{}'\n",
        shell_escape(&cert_b64),
        shell_escape(&key_b64)
    );

    let mut options = OpenOptions::new();
    options.create(true).write(true).truncate(true);
    #[cfg(unix)]
    options.mode(0o600);
    let mut file = options
        .open(output)
        .with_context(|| format!("failed to write {}", output.display()))?;
    file.write_all(body.as_bytes())?;
    println!("reverse tunnel identity written to {}", output.display());
    Ok(())
}

fn shell_escape(raw: &str) -> String {
    raw.replace('\'', "'\"'\"'")
}
