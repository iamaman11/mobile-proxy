use std::env;
use std::ffi::OsStr;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};

const PRODUCT_RELEASE_ASSET_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/product-release-asset/v2");

fn main() -> Result<()> {
    let mut arguments = env::args_os();
    let _binary = arguments.next();
    let asset_name = arguments
        .next()
        .context("Product Release asset name is required")?;
    let path = PathBuf::from(
        arguments
            .next()
            .context("Product Release asset path is required")?,
    );
    if arguments.next().is_some() {
        bail!("exactly one Product Release asset name and path are required");
    }
    if path.file_name() != Some(OsStr::new(&asset_name)) {
        bail!("Product Release asset name must equal the file basename");
    }
    let name = asset_name
        .to_str()
        .context("Product Release asset name must be valid UTF-8")?;
    if name.is_empty() || name.len() > 200 || name.contains('/') || name.contains('\\') {
        bail!("Product Release asset name is invalid");
    }
    let bytes = fs::read(&path)
        .with_context(|| format!("failed to read Product Release asset {}", path.display()))?;
    let digest = ContentDigest::derive(
        PRODUCT_RELEASE_ASSET_DOMAIN,
        [name.as_bytes(), bytes.as_slice()],
    );
    println!("{digest}");
    Ok(())
}
