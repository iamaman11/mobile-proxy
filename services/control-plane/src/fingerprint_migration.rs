use anyhow::{Context, Result, bail};
use proxy_core::{BinaryFingerprintInput, ConfigFingerprintInput};
use serde_json::Value;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct FingerprintMigrationStats {
    pub legacy_config_values: u64,
    pub legacy_binary_values: u64,
}

impl FingerprintMigrationStats {
    pub const fn total(self) -> u64 {
        self.legacy_config_values + self.legacy_binary_values
    }
}

pub fn normalize_persisted_fingerprints(body: &str) -> Result<(Value, FingerprintMigrationStats)> {
    let mut root: Value =
        serde_json::from_str(body).context("failed to parse stored state JSON")?;
    let Some(devices) = root.get_mut("devices").and_then(Value::as_object_mut) else {
        return Ok((root, FingerprintMigrationStats::default()));
    };
    let mut stats = FingerprintMigrationStats::default();
    for (device_id, device) in devices {
        let object = device
            .as_object_mut()
            .with_context(|| format!("stored device {device_id:?} must be a JSON object"))?;
        normalize_config_field(object.get_mut("config_fingerprint"), device_id, &mut stats)?;
        normalize_binary_field(object.get_mut("binary_fingerprint"), device_id, &mut stats)?;
    }
    Ok((root, stats))
}

fn normalize_config_field(
    value: Option<&mut Value>,
    device_id: &str,
    stats: &mut FingerprintMigrationStats,
) -> Result<()> {
    normalize_field(value, device_id, "config_fingerprint", |raw| {
        ConfigFingerprintInput::parse(raw).map(|value| value.is_legacy())
    })
    .map(|legacy| {
        if legacy {
            stats.legacy_config_values += 1;
        }
    })
}

fn normalize_binary_field(
    value: Option<&mut Value>,
    device_id: &str,
    stats: &mut FingerprintMigrationStats,
) -> Result<()> {
    normalize_field(value, device_id, "binary_fingerprint", |raw| {
        BinaryFingerprintInput::parse(raw).map(|value| value.is_legacy())
    })
    .map(|legacy| {
        if legacy {
            stats.legacy_binary_values += 1;
        }
    })
}

fn normalize_field(
    value: Option<&mut Value>,
    device_id: &str,
    field: &str,
    classify: impl FnOnce(&str) -> Result<bool, proxy_core::FingerprintInputError>,
) -> Result<bool> {
    let Some(value) = value else {
        return Ok(false);
    };
    if value.is_null() {
        return Ok(false);
    }
    let Some(raw) = value.as_str() else {
        bail!("stored device {device_id:?} field {field} must be a JSON string or null");
    };
    let legacy = classify(raw).with_context(|| {
        format!("stored device {device_id:?} field {field} uses an unsupported fingerprint")
    })?;
    if legacy {
        *value = Value::Null;
    }
    Ok(legacy)
}

#[cfg(test)]
mod tests {
    use proxy_core::{BinaryFingerprint, ConfigFingerprint};
    use serde_json::json;

    use super::normalize_persisted_fingerprints;

    #[test]
    fn legacy_values_are_dropped_for_typed_heartbeat_backfill() {
        let body = json!({
            "devices": {
                "node": {
                    "config_fingerprint": "legacy-config",
                    "binary_fingerprint": "legacy-binary"
                }
            },
            "commands": {"queues": {}, "idempotency": {}}
        })
        .to_string();
        let (normalized, stats) = normalize_persisted_fingerprints(&body).unwrap();
        assert_eq!(stats.legacy_config_values, 1);
        assert_eq!(stats.legacy_binary_values, 1);
        assert!(normalized["devices"]["node"]["config_fingerprint"].is_null());
        assert!(normalized["devices"]["node"]["binary_fingerprint"].is_null());
    }

    #[test]
    fn current_values_are_preserved_exactly() {
        let config = ConfigFingerprint::derive([b"config"]);
        let binary = BinaryFingerprint::derive([b"binary"]);
        let body = json!({
            "devices": {
                "node": {
                    "config_fingerprint": config,
                    "binary_fingerprint": binary
                }
            },
            "commands": {"queues": {}, "idempotency": {}}
        })
        .to_string();
        let (normalized, stats) = normalize_persisted_fingerprints(&body).unwrap();
        assert_eq!(stats.total(), 0);
        assert_eq!(
            normalized["devices"]["node"]["config_fingerprint"],
            config.to_string()
        );
        assert_eq!(
            normalized["devices"]["node"]["binary_fingerprint"],
            binary.to_string()
        );
    }

    #[test]
    fn unknown_prefixed_values_fail_closed() {
        let body = json!({
            "devices": {
                "node": {
                    "config_fingerprint": "unknown:abcd",
                    "binary_fingerprint": null
                }
            },
            "commands": {"queues": {}, "idempotency": {}}
        })
        .to_string();
        assert!(normalize_persisted_fingerprints(&body).is_err());
    }
}
