use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use proxy_core::{BinaryFingerprint, ConfigFingerprint};
use serde::de::{Error as DeError, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Number, Value};

const REDACTED_SECRET: &str = "<redacted>";

pub fn config_source_fingerprint(source: &[u8]) -> Result<ConfigFingerprint> {
    let mut deserializer = serde_json::Deserializer::from_slice(source);
    let unique = UniqueValue::deserialize(&mut deserializer)
        .context("host-daemon config contains invalid or ambiguous JSON")?;
    deserializer
        .end()
        .context("host-daemon config contains trailing JSON data")?;
    let canonical = canonicalize(unique.0, None);
    let bytes = serde_json::to_vec(&canonical).context("failed to encode canonical config")?;
    Ok(ConfigFingerprint::derive([bytes.as_slice()]))
}

pub fn binary_fingerprint(path: &Path) -> Result<BinaryFingerprint> {
    let bytes = fs::read(path)
        .with_context(|| format!("failed to read host-daemon binary {}", path.display()))?;
    Ok(BinaryFingerprint::derive([bytes.as_slice()]))
}

pub fn current_binary_fingerprint() -> Result<BinaryFingerprint> {
    #[cfg(any(target_os = "linux", target_os = "android"))]
    let path = Path::new("/proc/self/exe").to_path_buf();
    #[cfg(not(any(target_os = "linux", target_os = "android")))]
    let path = std::env::current_exe().context("failed to resolve host-daemon executable")?;
    binary_fingerprint(&path)
}

fn secret_key(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();
    matches!(
        normalized.as_str(),
        "admin_token"
            | "device_token"
            | "auth_token"
            | "username"
            | "password"
            | "private_key"
            | "server_key_der_b64"
    ) || normalized.ends_with("_token")
        || normalized.ends_with("_password")
        || normalized.ends_with("_secret")
        || normalized.ends_with("_private_key")
}

fn canonicalize(value: Value, key: Option<&str>) -> Value {
    if key.is_some_and(secret_key) {
        return Value::String(REDACTED_SECRET.into());
    }
    match value {
        Value::Array(values) => Value::Array(
            values
                .into_iter()
                .map(|value| canonicalize(value, None))
                .collect(),
        ),
        Value::Object(values) => {
            let sorted: BTreeMap<String, Value> = values.into_iter().collect();
            let mut canonical = Map::new();
            for (field, value) in sorted {
                canonical.insert(field.clone(), canonicalize(value, Some(&field)));
            }
            Value::Object(canonical)
        }
        scalar => scalar,
    }
}

struct UniqueValue(Value);

impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(UniqueValueVisitor)
    }
}

struct UniqueValueVisitor;

impl<'de> Visitor<'de> for UniqueValueVisitor {
    type Value = UniqueValue;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::Null))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::Null))
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::Bool(value)))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::Number(Number::from(value))))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::Number(Number::from(value))))
    }
    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Number::from_f64(value)
            .map(Value::Number)
            .map(UniqueValue)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::String(value.into())))
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
    where
        E: DeError,
    {
        Ok(UniqueValue(Value::String(value)))
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element::<UniqueValue>()? {
            values.push(value.0);
        }
        Ok(UniqueValue(Value::Array(values)))
    }

    fn visit_map<A>(self, mut object: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = BTreeMap::new();
        while let Some(field) = object.next_key::<String>()? {
            if values.contains_key(&field) {
                return Err(A::Error::custom(format!(
                    "duplicate JSON object key {field:?}"
                )));
            }
            let value = object.next_value::<UniqueValue>()?;
            values.insert(field, value.0);
        }
        Ok(UniqueValue(Value::Object(values.into_iter().collect())))
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use uuid::Uuid;

    use super::{binary_fingerprint, config_source_fingerprint};

    #[test]
    fn config_fingerprint_is_canonical_and_secret_independent() {
        let first = br#"{
            "node_name": "phone",
            "admin_token": "first-secret",
            "proxy": {"password": "first", "listen_address": "10.0.0.1:1080"}
        }"#;
        let reordered = br#"{"proxy":{"listen_address":"10.0.0.1:1080","password":"second"},"admin_token":"second-secret","node_name":"phone"}"#;
        assert_eq!(
            config_source_fingerprint(first).unwrap(),
            config_source_fingerprint(reordered).unwrap()
        );
        assert_ne!(
            config_source_fingerprint(first).unwrap(),
            config_source_fingerprint(
                br#"{"node_name":"other","admin_token":"first-secret","proxy":{"password":"first","listen_address":"10.0.0.1:1080"}}"#
            )
            .unwrap()
        );
    }

    #[test]
    fn config_fingerprint_rejects_ambiguous_duplicate_keys() {
        assert!(config_source_fingerprint(br#"{"node_name":"a","node_name":"b"}"#).is_err());
    }

    #[test]
    fn binary_fingerprint_uses_exact_binary_bytes() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-host-binary-fingerprint-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        let binary = root.join("host-daemon");
        fs::write(&binary, b"first").unwrap();
        let first = binary_fingerprint(&binary).unwrap();
        fs::write(&binary, b"second").unwrap();
        let second = binary_fingerprint(&binary).unwrap();
        assert_ne!(first, second);
        let _ = fs::remove_dir_all(root);
    }
}
