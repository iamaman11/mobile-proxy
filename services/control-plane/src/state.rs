use std::collections::{HashMap, VecDeque};
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::{Context, Result};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

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
            Ok(body) => serde_json::from_str(&body)
                .with_context(|| format!("failed to parse {}", state_path.display()))?,
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
        let body = serde_json::to_vec_pretty(&stored)?;
        if let Some(parent) = self.state_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let tmp = self.state_path.with_extension("json.tmp");
        fs::write(&tmp, body)?;
        fs::rename(&tmp, self.state_path.as_ref())?;
        Ok(())
    }
}
