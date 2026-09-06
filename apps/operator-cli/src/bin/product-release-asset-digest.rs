use std::env;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};

const PRODUCT_RELEASE_ASSET_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/product-release-asset/v2");

fn validate_asset_name(name: &str) -> Result<()> {
    if name.is_empty()
        || name.len() > 200
        || name.starts_with('/')
        || name.ends_with('/')
        || name.contains('\\')
        || name.chars().any(char::is_control)
    {
        bail!("Product Release asset name is invalid");
    }
    if name
        .split('/')
        .any(|component| component.is_empty() || component == "." || component == "..")
    {
        bail!("Product Release asset name is invalid");
    }
    Ok(())
}

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
    let name = asset_name
        .to_str()
        .context("Product Release asset name must be valid UTF-8")?;
    validate_asset_name(name)?;
    let bytes = fs::read(&path)
        .with_context(|| format!("failed to read Product Release asset {}", path.display()))?;
    let digest = ContentDigest::derive(
        PRODUCT_RELEASE_ASSET_DOMAIN,
        [name.as_bytes(), bytes.as_slice()],
    );
    println!("{digest}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::validate_asset_name;

    #[test]
    fn accepts_top_level_and_nested_logical_asset_names() {
        for name in [
            "release-manifest.json",
            "mobile-proxy-linux-x86_64-v0.1.7.tar.gz",
            "phone-production-runtime/bin/runtime-supervisor",
            "phone-production-runtime/bin/host-daemon",
            "phone-production-runtime/bin/sing-box",
            "phone-production-runtime/components.json",
        ] {
            assert!(validate_asset_name(name).is_ok(), "expected valid name: {name}");
        }
    }

    #[test]
    fn rejects_unsafe_logical_asset_names() {
        for name in [
            "",
            "/absolute/path",
            "phone-production-runtime/../escape",
            "phone-production-runtime/./runtime-supervisor",
            "phone-production-runtime//runtime-supervisor",
            "phone-production-runtime/",
            "phone-production-runtime\\bin\\runtime-supervisor",
            "phone-production-runtime/bin/runtime-supervisor\nother",
        ] {
            assert!(validate_asset_name(name).is_err(), "expected invalid name: {name:?}");
        }
    }
}
