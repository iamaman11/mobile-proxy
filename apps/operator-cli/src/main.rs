mod android_app;
mod artifacts;
mod cli;
mod commands;
mod device;
mod device_stack;
mod http;
mod provision;
mod vm;

use anyhow::{Context, Result};
use clap::Parser;
use std::env;
use std::time::Duration;

use crate::cli::{Cli, Command};
use crate::commands::{run_airplane_study, run_proxy, run_rotate, run_status};
use crate::device::{install_device_release, rollback_device, verify_device};
use crate::provision::package_device_release;
use crate::vm::{delete_vm, provision_vm};

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .context("failed to build HTTP client")?;

    match cli.command {
        Command::Status => {
            let token = resolve_token(cli.token.as_deref())?;
            run_status(&client, &cli.api, &token).await?
        }
        Command::Proxy => run_proxy()?,
        Command::Rotate(args) => {
            let token = resolve_token(cli.token.as_deref())?;
            run_rotate(&client, &cli.api, &token, &args).await?
        }
        Command::AirplaneStudy(args) => {
            let token = resolve_token(cli.token.as_deref())?;
            run_airplane_study(&client, &cli.api, &token, &args).await?
        }
        Command::PrepareRuntimeBinaries(args) => artifacts::prepare_runtime_binaries(&args)?,
        Command::ProvisionVm(args) => provision_vm(&args)?,
        Command::DeleteVm(args) => delete_vm(&args)?,
        Command::InstallAndroidApp(args) => android_app::install_android_app(&args)?,
        Command::InstallDeviceStack(args) => device_stack::install_device_stack(&args).await?,
        Command::PackageDeviceRelease(args) => package_device_release(&args)?,
        Command::InstallDeviceRelease(args) => install_device_release(&args).await?,
        Command::VerifyDevice(args) => verify_device(&args).await?,
        Command::RollbackDevice(args) => rollback_device(&args).await?,
    }

    Ok(())
}

fn resolve_token(cli_token: Option<&str>) -> Result<String> {
    cli_token
        .map(ToOwned::to_owned)
        .or_else(|| env::var("MOBILE_PROXY_ADMIN_TOKEN").ok())
        .context("missing token: pass --token or set MOBILE_PROXY_ADMIN_TOKEN")
}
