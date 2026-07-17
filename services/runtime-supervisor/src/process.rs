use std::fs::OpenOptions;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::process::{Child, Command, Stdio};

use anyhow::{Context, Result, bail};
use tracing::{info, warn};

use crate::android::tun0_ready;
use crate::config::{SupervisorConfig, TunnelOwner};

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
            if config.tunnel_owner == TunnelOwner::FirstPartyReverseTunnel {
                restart_host_daemon_after_proxy_exit(&mut self.host_daemon);
            }
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

    pub fn restart_proxy(&mut self, config: &SupervisorConfig) {
        let Some(mut proxy) = self.proxy.take() else {
            return;
        };
        info!("proxy configuration changed; restarting proxy");
        if let Err(err) = proxy.kill() {
            warn!("failed to stop proxy for configuration reload: {err:#}");
        }
        let _ = proxy.wait();
        if config.tunnel_owner == TunnelOwner::FirstPartyReverseTunnel {
            restart_host_daemon_after_proxy_exit(&mut self.host_daemon);
        }
    }
}

fn restart_host_daemon_after_proxy_exit(host_daemon: &mut Option<Child>) {
    let Some(mut child) = host_daemon.take() else {
        return;
    };
    warn!(
        "proxy exited under first-party reverse tunnel; restarting host-daemon to refresh QUIC session"
    );
    if let Err(err) = child.kill() {
        warn!("failed to kill host-daemon after proxy exit: {err:#}");
    }
    let _ = child.wait();
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
    let stdout = append_log("/data/local/tmp/mobile-proxy-logs/host-daemon.log")?;
    let stderr = stdout
        .try_clone()
        .context("failed to clone host-daemon log")?;
    let child = Command::new(&config.host_binary)
        .arg("--config")
        .arg(&config.host_config)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.host_binary.display()))?;
    info!("host-daemon spawned pid={}", child.id());
    Ok(child)
}

fn spawn_proxy(config: &SupervisorConfig) -> Result<Child> {
    ensure_executable(&config.proxy_binary)?;
    let stdout = append_log("/data/local/tmp/mobile-proxy-logs/sing-box.log")?;
    let stderr = stdout.try_clone().context("failed to clone sing-box log")?;
    let child = Command::new(&config.proxy_binary)
        .args(&config.proxy_args)
        .current_dir(&config.proxy_working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.proxy_binary.display()))?;
    info!("proxy spawned pid={}", child.id());
    Ok(child)
}

fn append_log(path: &str) -> Result<std::fs::File> {
    rotate_log(path, 5 * 1024 * 1024)?;
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open runtime log {path}"))?;
    #[cfg(unix)]
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
        .with_context(|| format!("failed to secure runtime log {path}"))?;
    Ok(file)
}

fn rotate_log(path: &str, max_bytes: u64) -> Result<()> {
    let Ok(metadata) = std::fs::metadata(path) else {
        return Ok(());
    };
    if metadata.len() < max_bytes {
        return Ok(());
    }
    let rotated = format!("{path}.1");
    if std::path::Path::new(&rotated).exists() {
        std::fs::remove_file(&rotated)
            .with_context(|| format!("failed to remove old rotated log {rotated}"))?;
    }
    std::fs::rename(path, &rotated).with_context(|| format!("failed to rotate runtime log {path}"))
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
