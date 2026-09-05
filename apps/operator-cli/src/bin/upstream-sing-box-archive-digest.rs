use std::env;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};

const SING_BOX_ARCHIVE_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/upstream-sing-box-archive/v1");

fn main() -> Result<()> {
    let mut arguments = env::args_os();
    let _binary = arguments.next();
    let path = PathBuf::from(
        arguments
            .next()
            .context("sing-box archive path is required")?,
    );
    if arguments.next().is_some() {
        bail!("exactly one sing-box archive path is required");
    }
    if !path.is_file() {
        bail!("sing-box archive path is not a file: {}", path.display());
    }
    let bytes = fs::read(&path)
        .with_context(|| format!("failed to read sing-box archive {}", path.display()))?;
    let digest = ContentDigest::derive(SING_BOX_ARCHIVE_DOMAIN, [bytes.as_slice()]);
    println!("{digest}");
    Ok(())
}
