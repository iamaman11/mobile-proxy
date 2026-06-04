use std::path::Path;
use std::process::{Child, Command, Stdio};

use anyhow::{Context, Result, bail};
use tracing::{info, warn};

use crate::android::tun0_ready;
use crate::config::SupervisorConfig;

const STALE_RUNTIME_PATTERNS: &[&str] = &[
    "/data/adb/mobile-proxy-node/.*/bin/runtime-supervisor",
    "/data/adb/mobile-proxy-node/.*/bin/host-daemon",
    "/data/adb/mobile-proxy-node/.*/bin/sing-box",
    "/data/adb/mobile-proxy-node/.*/service.sh --route-guard",
];

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

        if self.proxy.is_none() && proxy_start_allowed(config) {
            self.proxy = Some(spawn_proxy(config)?);
        }
        if self.host_daemon.is_none() {
            self.host_daemon = Some(spawn_host_daemon(config)?);
        }
        Ok(())
    }
}

fn proxy_start_allowed(config: &SupervisorConfig) -> bool {
    if !config.wireguard_enabled {
        return true;
    }
    let ready = tun0_ready();
    if !ready {
        warn!("wireguard is enabled but tun0 is absent; deferring proxy start");
    }
    ready
}

pub fn cleanup_stale_runtime_processes() {
    let current_pid = std::process::id();
    for pattern in STALE_RUNTIME_PATTERNS {
        match matching_pids(pattern) {
            Ok(pids) => terminate_stale_pids(pattern, current_pid, &pids),
            Err(err) => warn!("could not list stale processes for {pattern}: {err:#}"),
        }
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

fn matching_pids(pattern: &str) -> Result<Vec<u32>> {
    let output = Command::new("pgrep")
        .args(["-f", pattern])
        .output()
        .with_context(|| format!("failed to run pgrep for {pattern}"))?;
    if !output.status.success() {
        return Ok(Vec::new());
    }

    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| line.trim().parse::<u32>().ok())
        .collect())
}

fn terminate_stale_pids(pattern: &str, current_pid: u32, pids: &[u32]) {
    for pid in pids {
        if *pid == current_pid {
            continue;
        }

        info!(
            "terminating stale runtime process pid={} pattern={}",
            pid, pattern
        );
        if let Err(err) = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status()
        {
            warn!("failed to SIGTERM stale pid {}: {err:#}", pid);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::terminate_stale_pids;

    #[test]
    fn stale_termination_skips_current_pid() {
        terminate_stale_pids("test-pattern", std::process::id(), &[std::process::id()]);
    }
}
