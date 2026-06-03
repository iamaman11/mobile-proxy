use std::collections::HashMap;
use std::sync::Arc;

use proxy_core::{HealthRecord, JobRecord};
use tokio::sync::Mutex;
use uuid::Uuid;

#[derive(Clone)]
pub struct AppState {
    pub admin_token: String,
    pub runtime: SharedRuntime,
}

pub type SharedRuntime = Arc<Mutex<RuntimeState>>;

pub struct RuntimeState {
    pub health: HealthRecord,
    pub jobs: HashMap<Uuid, JobRecord>,
    pub current_job: Option<Uuid>,
    pub wireguard_enabled: bool,
    pub proxy_listen_address: String,
    pub proxy_pid: Option<u32>,
    pub rotation_commands: RotationCommands,
    pub observer_urls: Vec<String>,
}

#[derive(Debug, Clone, Default)]
pub struct RotationCommands {
    pub data_reconnect: Option<String>,
    pub airplane_bounce: Option<String>,
    pub network_mode_bounce: Option<String>,
    pub ril_bounce: Option<String>,
}

impl RuntimeState {
    pub fn new(
        health: HealthRecord,
        wireguard_enabled: bool,
        proxy_listen_address: String,
        rotation_commands: RotationCommands,
        observer_urls: Vec<String>,
    ) -> Self {
        Self {
            health,
            jobs: HashMap::new(),
            current_job: None,
            wireguard_enabled,
            proxy_listen_address,
            proxy_pid: None,
            rotation_commands,
            observer_urls,
        }
    }
}
