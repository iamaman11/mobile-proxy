use std::error::Error;
use std::fmt::{Display, Formatter};

use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use serde::{Deserialize, Deserializer, Serialize, Serializer};

pub const CONFIG_FINGERPRINT_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/host-daemon-nonsecret-config/v1");
pub const BINARY_FINGERPRINT_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/host-daemon-binary/v1");

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ConfigFingerprint(ContentDigest);

impl ConfigFingerprint {
    pub fn derive<I, B>(parts: I) -> Self
    where
        I: IntoIterator<Item = B>,
        B: AsRef<[u8]>,
    {
        Self(ContentDigest::derive(CONFIG_FINGERPRINT_DOMAIN, parts))
    }

    pub const fn content_digest(self) -> ContentDigest {
        self.0
    }
}

impl Display for ConfigFingerprint {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        Display::fmt(&self.0, formatter)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct BinaryFingerprint(ContentDigest);

impl BinaryFingerprint {
    pub fn derive<I, B>(parts: I) -> Self
    where
        I: IntoIterator<Item = B>,
        B: AsRef<[u8]>,
    {
        Self(ContentDigest::derive(BINARY_FINGERPRINT_DOMAIN, parts))
    }

    pub const fn content_digest(self) -> ContentDigest {
        self.0
    }
}

impl Display for BinaryFingerprint {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        Display::fmt(&self.0, formatter)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FingerprintInputError {
    UnsupportedAlgorithmDomainOrVersion,
    InvalidLegacyValue,
}

impl Display for FingerprintInputError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsupportedAlgorithmDomainOrVersion => {
                formatter.write_str("fingerprint algorithm, domain or version is unsupported")
            }
            Self::InvalidLegacyValue => formatter.write_str("legacy fingerprint value is invalid"),
        }
    }
}

impl Error for FingerprintInputError {}

fn legacy_opaque_value(raw: &str) -> bool {
    !raw.is_empty()
        && raw.len() <= 256
        && !raw.contains(':')
        && raw.bytes().all(|byte| byte.is_ascii_graphic())
}

macro_rules! migrating_fingerprint_input {
    ($name:ident, $current:ty) => {
        #[derive(Debug, Clone, PartialEq, Eq)]
        pub struct $name(FingerprintInputValue<$current>);

        impl $name {
            pub const fn current(value: $current) -> Self {
                Self(FingerprintInputValue::Current(value))
            }

            pub fn parse(raw: &str) -> Result<Self, FingerprintInputError> {
                if raw.starts_with("b3:") {
                    return serde_json::from_value::<$current>(serde_json::Value::String(
                        raw.to_owned(),
                    ))
                    .map(|value| Self(FingerprintInputValue::Current(value)))
                    .map_err(|_| FingerprintInputError::UnsupportedAlgorithmDomainOrVersion);
                }
                if raw.contains(':') {
                    return Err(FingerprintInputError::UnsupportedAlgorithmDomainOrVersion);
                }
                if legacy_opaque_value(raw) {
                    return Ok(Self(FingerprintInputValue::LegacyOpaque(raw.into())));
                }
                Err(FingerprintInputError::InvalidLegacyValue)
            }

            pub const fn current_value(&self) -> Option<$current> {
                match &self.0 {
                    FingerprintInputValue::Current(value) => Some(*value),
                    FingerprintInputValue::LegacyOpaque(_) => None,
                }
            }

            pub const fn is_legacy(&self) -> bool {
                matches!(&self.0, FingerprintInputValue::LegacyOpaque(_))
            }
        }

        impl Serialize for $name {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                match &self.0 {
                    FingerprintInputValue::Current(value) => value.serialize(serializer),
                    FingerprintInputValue::LegacyOpaque(value) => serializer.serialize_str(value),
                }
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let raw = String::deserialize(deserializer)?;
                Self::parse(&raw).map_err(<D::Error as serde::de::Error>::custom)
            }
        }
    };
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum FingerprintInputValue<T> {
    Current(T),
    LegacyOpaque(Box<str>),
}

migrating_fingerprint_input!(ConfigFingerprintInput, ConfigFingerprint);
migrating_fingerprint_input!(BinaryFingerprintInput, BinaryFingerprint);

pub fn deserialize_optional_config_fingerprint<'de, D>(
    deserializer: D,
) -> Result<Option<ConfigFingerprint>, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    raw.map(|raw| {
        ConfigFingerprintInput::parse(&raw)
            .map(|value| value.current_value())
            .map_err(<D::Error as serde::de::Error>::custom)
    })
    .transpose()
    .map(Option::flatten)
}

pub fn deserialize_optional_binary_fingerprint<'de, D>(
    deserializer: D,
) -> Result<Option<BinaryFingerprint>, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    raw.map(|raw| {
        BinaryFingerprintInput::parse(&raw)
            .map(|value| value.current_value())
            .map_err(<D::Error as serde::de::Error>::custom)
    })
    .transpose()
    .map(Option::flatten)
}

#[cfg(test)]
mod tests {
    use super::{
        BinaryFingerprint, BinaryFingerprintInput, ConfigFingerprint, ConfigFingerprintInput,
        deserialize_optional_binary_fingerprint, deserialize_optional_config_fingerprint,
    };

    #[test]
    fn field_specific_fingerprints_use_distinct_domains() {
        let bytes = b"same bytes";
        let config = ConfigFingerprint::derive([bytes.as_slice()]);
        let binary = BinaryFingerprint::derive([bytes.as_slice()]);
        assert_ne!(config.content_digest(), binary.content_digest());
    }

    #[test]
    fn current_wire_values_remain_json_strings() {
        let current = ConfigFingerprintInput::current(ConfigFingerprint::derive([b"config"]));
        let json = serde_json::to_string(&current).unwrap();
        assert!(json.starts_with("\"b3:"));
        assert_eq!(
            serde_json::from_str::<ConfigFingerprintInput>(&json).unwrap(),
            current
        );
    }

    #[test]
    fn isolated_legacy_reader_accepts_only_bounded_unprefixed_values() {
        let legacy = ConfigFingerprintInput::parse("legacy-value").unwrap();
        assert!(legacy.is_legacy());
        assert_eq!(serde_json::to_string(&legacy).unwrap(), "\"legacy-value\"");
        assert!(
            BinaryFingerprintInput::parse(&"a".repeat(64))
                .unwrap()
                .is_legacy()
        );
        assert!(ConfigFingerprintInput::parse("unknown:abcd").is_err());
        assert!(ConfigFingerprintInput::parse("b3:not-a-digest").is_err());
        assert!(ConfigFingerprintInput::parse("contains space").is_err());
        assert!(ConfigFingerprintInput::parse(&"x".repeat(257)).is_err());
    }

    #[derive(serde::Deserialize)]
    struct CompatibleRecord {
        #[serde(default, deserialize_with = "deserialize_optional_config_fingerprint")]
        config: Option<ConfigFingerprint>,
        #[serde(default, deserialize_with = "deserialize_optional_binary_fingerprint")]
        binary: Option<BinaryFingerprint>,
    }

    #[test]
    fn canonical_record_reader_drops_legacy_but_rejects_unknown_prefixes() {
        let legacy: CompatibleRecord =
            serde_json::from_str(r#"{"config":"legacy-config","binary":"reconstructed"}"#).unwrap();
        assert!(legacy.config.is_none());
        assert!(legacy.binary.is_none());
        assert!(
            serde_json::from_str::<CompatibleRecord>(r#"{"config":"unknown:abcd","binary":null}"#)
                .is_err()
        );
    }
}
