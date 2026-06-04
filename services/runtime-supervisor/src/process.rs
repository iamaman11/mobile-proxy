use std::path::Path;
use std::process::{Child, Command, Stdio};

use anyhow::{Context, Result, bail};
use tracing::{info, warn};

use crate::config::SupervisorConfig;

pub struct RuntimeChildren {
    host_daemon: Option<Child>,
    proxy: Option<Child>,
}

impl RuntimeChildren {
    pub fn new() -> Self {
        Self {
            host_daemon: None,
            proxy: None,
        }
    }

    pub fn ensure(&mut self, config: &SupervisorConfig) -> Result<()> {
        if child_exited(&mut self.proxy)? {
            warn!("proxy process exited; restarting");
            self.proxy = None;
        }
        if child_exited(&mut self.host_daemon)? {
            warn!("host-daemon process exited; restarting");
            self.host_daemon = None;
        }

        if self.proxy.is_none() {
            self.proxy = Some(spawn_proxy(config)?);
        }
        if self.host_daemon.is_none() {
            self.host_daemon = Some(spawn_host_daemon(config)?);
        }
        Ok(())
    }
}

fn child_exited(child: &mut Option<Child>) -> Result<bool> {
    let Some(child) = child else {
        return Ok(false);
    };
    Ok(child.try_wait()?.is_some())
}

fn spawn_host_daemon(config: &SupervisorConfig) -> Result<Child> {
    ensure_executable(&config.host_binary)?;
    let child = Command::new(&config.host_binary)
        .arg("--config")
        .arg(&config.host_config)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.host_binary.display()))?;
    info!("host-daemon spawned pid={}", child.id());
    Ok(child)
}

fn spawn_proxy(config: &SupervisorConfig) -> Result<Child> {
    ensure_executable(&config.proxy_binary)?;
    let child = Command::new(&config.proxy_binary)
        .args(&config.proxy_args)
        .current_dir(&config.proxy_working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.proxy_binary.display()))?;
    info!("proxy spawned pid={}", child.id());
    Ok(child)
}

fn ensure_executable(path: &Path) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        bail!("missing runtime binary: {}", path.display())
    }
}
