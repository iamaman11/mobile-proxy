use std::fs::{self, File, OpenOptions};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use reverse_tunnel::TunnelEventCounters;
use serde::{Deserialize, Serialize};

const COUNTER_SCHEMA_VERSION: u16 = 1;
const MAX_COUNTER_FILE_BYTES: u64 = 16 * 1024;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PersistedTunnelCounters {
    schema_version: u16,
    counters: TunnelEventCounters,
}

#[derive(Debug)]
pub struct TunnelCounterStore {
    path: PathBuf,
    current: TunnelEventCounters,
}

impl TunnelCounterStore {
    pub fn load(path: PathBuf) -> Result<Self> {
        let metadata = match fs::metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == ErrorKind::NotFound => {
                return Ok(Self {
                    path,
                    current: TunnelEventCounters::default(),
                });
            }
            Err(error) => return Err(error).context("failed to inspect tunnel counter state"),
        };
        if metadata.len() > MAX_COUNTER_FILE_BYTES {
            bail!("tunnel counter state exceeds bounded file size");
        }
        let body = fs::read(&path).context("failed to read tunnel counter state")?;
        let persisted: PersistedTunnelCounters =
            serde_json::from_slice(&body).context("failed to decode tunnel counter state")?;
        if persisted.schema_version != COUNTER_SCHEMA_VERSION {
            bail!("unsupported tunnel counter state schema version");
        }
        Ok(Self {
            path,
            current: persisted.counters,
        })
    }

    pub fn counters(&self) -> &TunnelEventCounters {
        &self.current
    }

    pub fn persist_if_changed(&mut self, counters: &TunnelEventCounters) -> Result<bool> {
        if self.current.same_persisted_state(counters) {
            return Ok(false);
        }
        write_atomic(&self.path, counters)?;
        self.current = counters.clone();
        Ok(true)
    }
}

fn write_atomic(path: &Path, counters: &TunnelEventCounters) -> Result<()> {
    let persisted = PersistedTunnelCounters {
        schema_version: COUNTER_SCHEMA_VERSION,
        counters: counters.clone(),
    };
    let body = serde_json::to_vec(&persisted).context("failed to encode tunnel counter state")?;
    if body.len() as u64 > MAX_COUNTER_FILE_BYTES {
        bail!("encoded tunnel counter state exceeds bounded file size");
    }
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        fs::create_dir_all(parent).context("failed to create tunnel counter state directory")?;
    }
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .context("tunnel counter state path has no UTF-8 file name")?;
    let temporary = path.with_file_name(format!(".{file_name}.tmp-{}", std::process::id()));
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temporary)
        .context("failed to create temporary tunnel counter state")?;
    file.write_all(&body)
        .context("failed to write temporary tunnel counter state")?;
    file.sync_all()
        .context("failed to sync temporary tunnel counter state")?;
    fs::rename(&temporary, path).context("failed to atomically replace tunnel counter state")?;
    #[cfg(unix)]
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        File::open(parent)
            .and_then(|directory| directory.sync_all())
            .context("failed to sync tunnel counter state directory")?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use reverse_tunnel::{TunnelActiveTransport, TunnelFailoverReason, TunnelTransportTransition};
    use uuid::Uuid;

    #[test]
    fn state_round_trips_atomically_and_duplicate_snapshot_does_not_rewrite() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-test-{}",
            Uuid::new_v4()
        ));
        let path = directory.join("counters.json");
        let mut store = TunnelCounterStore::load(path.clone()).unwrap();
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_connection(TunnelActiveTransport::TlsTcp);

        assert!(store.persist_if_changed(&counters).unwrap());
        assert!(!store.persist_if_changed(&counters).unwrap());
        let reloaded = TunnelCounterStore::load(path).unwrap();
        assert!(reloaded.counters().same_persisted_state(&counters));
        assert_eq!(
            reloaded
                .counters()
                .transition_count(TunnelTransportTransition::NoneToTlsTcp),
            1
        );
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn failed_write_does_not_advance_state_and_is_retryable() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-retry-test-{}",
            Uuid::new_v4()
        ));
        let blocking_parent = directory.join("state");
        let path = blocking_parent.join("counters.json");
        let mut store = TunnelCounterStore::load(path.clone()).unwrap();
        fs::create_dir_all(&directory).unwrap();
        fs::write(&blocking_parent, b"not-a-directory").unwrap();

        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_connection(TunnelActiveTransport::Quic);
        assert!(store.persist_if_changed(&counters).is_err());
        assert!(!store.counters().same_persisted_state(&counters));

        fs::remove_file(&blocking_parent).unwrap();
        fs::create_dir_all(&blocking_parent).unwrap();
        assert!(store.persist_if_changed(&counters).unwrap());
        let reloaded = TunnelCounterStore::load(path).unwrap();
        assert!(reloaded.counters().same_persisted_state(&counters));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn invalid_schema_fails_closed() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-schema-test-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("counters.json");
        let body = serde_json::json!({
            "schema_version": 999,
            "counters": TunnelEventCounters::default(),
        });
        fs::write(&path, serde_json::to_vec(&body).unwrap()).unwrap();
        let error = TunnelCounterStore::load(path).unwrap_err();
        assert!(error.to_string().contains("unsupported"));
        fs::remove_dir_all(directory).unwrap();
    }
}
