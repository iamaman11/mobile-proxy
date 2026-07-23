use std::collections::{HashMap, VecDeque};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

use crate::fingerprint_migration::normalize_persisted_fingerprints;

#[derive(Clone)]
pub struct AppState {
    pub devices: Arc<Mutex<HashMap<String, DeviceRecord>>>,
    pub commands: Arc<Mutex<CommandState>>,
    state_path: Arc<PathBuf>,
}

#[derive(Default, Clone, Serialize, Deserialize)]
pub struct CommandState {
    pub queues: HashMap<String, VecDeque<DeviceCommand>>,
    pub idempotency: HashMap<String, CommandId>,
}

#[derive(Default, Serialize, Deserialize)]
struct StoredState {
    devices: HashMap<String, DeviceRecord>,
    commands: CommandState,
}

impl AppState {
    pub async fn load(state_path: PathBuf) -> Result<Self> {
        let stored = match fs::read_to_string(&state_path) {
            Ok(body) => {
                let (normalized, migration) = normalize_persisted_fingerprints(&body)
                    .with_context(|| format!("failed to migrate {}", state_path.display()))?;
                let stored: StoredState = serde_json::from_value(normalized)
                    .with_context(|| format!("failed to parse {}", state_path.display()))?;
                if migration.total() > 0 {
                    write_stored_state(&state_path, &stored).with_context(|| {
                        format!("failed to persist migrated {}", state_path.display())
                    })?;
                    tracing::warn!(
                        legacy_config_fingerprints = migration.legacy_config_values,
                        legacy_binary_fingerprints = migration.legacy_binary_values,
                        "legacy persisted fingerprints removed for typed heartbeat backfill"
                    );
                }
                stored
            }
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => StoredState::default(),
            Err(err) => {
                return Err(err)
                    .with_context(|| format!("failed to read {}", state_path.display()));
            }
        };
        Ok(Self {
            devices: Arc::new(Mutex::new(stored.devices)),
            commands: Arc::new(Mutex::new(stored.commands)),
            state_path: Arc::new(state_path),
        })
    }

    pub async fn persist(&self) -> Result<()> {
        let stored = StoredState {
            devices: self.devices.lock().await.clone(),
            commands: self.commands.lock().await.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
    }
}

fn write_stored_state(path: &Path, stored: &StoredState) -> Result<()> {
    let body = serde_json::to_vec_pretty(stored)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let mut file = fs::File::create(&tmp)?;
    file.write_all(&body)?;
    file.sync_all()?;
    drop(file);
    fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::json;
    use uuid::Uuid;

    use super::AppState;

    #[tokio::test]
    async fn legacy_fingerprint_migration_is_restart_safe() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-fingerprint-migration-{}.json",
            Uuid::new_v4()
        ));
        fs::write(
            &path,
            serde_json::to_vec_pretty(&json!({
                "devices": {
                    "node": {
                        "node_id": "node",
                        "node_name": "node",
                        "readiness_state": "booting",
                        "serving": false,
                        "proxy_status": "starting",
                        "proxy_pid": null,
                        "last_public_ip": null,
                        "current_job": null,
                        "last_proxy_error": null,
                        "version": null,
                        "config_fingerprint": "legacy-config",
                        "binary_fingerprint": "legacy-binary",
                        "active_operator_profile": null,
                        "active_operator_plmn": null,
                        "publicly_serving": false,
                        "public_probe_error": null,
                        "public_probe_at": null,
                        "cellular_route_ready": null,
                        "proxy_bind_ready": null,
                        "local_serving_ready": null,
                        "tun0_present": null,
                        "wg_handshake_recent": null,
                        "reverse_tunnel_connected": null,
                        "reverse_tunnel_last_error": null,
                        "reverse_tunnel_active_transport": null,
                        "reverse_tunnel_freshness": null,
                        "reverse_tunnel_failover_reason": null,
                        "tunnel_owner": null,
                        "last_heartbeat_at": null,
                        "availability": "degraded",
                        "degradation_reason_code": null,
                        "serving_failure_reason": null,
                        "desired_state": null,
                        "recovery_intent": null,
                        "last_event_at": null
                    }
                },
                "commands": {"queues": {}, "idempotency": {}}
            }))
            .unwrap(),
        )
        .unwrap();

        let first = AppState::load(path.clone()).await.unwrap();
        let device = first.devices.lock().await.get("node").unwrap().clone();
        assert!(device.config_fingerprint.is_none());
        assert!(device.binary_fingerprint.is_none());
        drop(first);

        let second = AppState::load(path.clone()).await.unwrap();
        let device = second.devices.lock().await.get("node").unwrap().clone();
        assert!(device.config_fingerprint.is_none());
        assert!(device.binary_fingerprint.is_none());
        let _ = fs::remove_file(path);
    }
}
