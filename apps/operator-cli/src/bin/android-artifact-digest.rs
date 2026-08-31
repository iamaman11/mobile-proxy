use std::env;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};

const ANDROID_ARTIFACT_DOMAIN: DigestDomain = DigestDomain::new("mobile-proxy/android-apk/v1");

fn main() -> Result<()> {
    let mut arguments = env::args_os();
    let _binary = arguments.next();
    let path = PathBuf::from(
        arguments
            .next()
            .context("Android artifact path is required")?,
    );
    if arguments.next().is_some() {
        bail!("exactly one Android artifact path is required");
    }
    let bytes = fs::read(&path)
        .with_context(|| format!("failed to read Android artifact {}", path.display()))?;
    let digest = ContentDigest::derive(ANDROID_ARTIFACT_DOMAIN, [bytes.as_slice()]);
    println!("{digest}");
    Ok(())
}
