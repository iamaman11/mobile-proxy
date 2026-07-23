use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::error::Error;
use std::fmt::{Display, Formatter};
use std::str::FromStr;
use uuid::Uuid;

pub const MAX_IDENTITY_LENGTH: usize = 64;
pub const MAX_IDEMPOTENCY_KEY_LENGTH: usize = 128;
pub const MAX_DEADLINE_WINDOW_SECS: u32 = 86_400;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FoundationError {
    Empty(&'static str),
    TooLong { field: &'static str, max: usize },
    InvalidCharacters(&'static str),
    InvalidUuid(&'static str),
    InvalidDeadlineWindow,
    DeadlineOverflow,
    InvalidDigest,
}

impl Display for FoundationError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Empty(field) => write!(formatter, "{field} must not be empty"),
            Self::TooLong { field, max } => {
                write!(formatter, "{field} exceeds the maximum length of {max}")
            }
            Self::InvalidCharacters(field) => {
                write!(formatter, "{field} contains unsupported characters")
            }
            Self::InvalidUuid(field) => write!(formatter, "{field} must be a UUID"),
            Self::InvalidDeadlineWindow => write!(
                formatter,
                "deadline window must be between 1 and {MAX_DEADLINE_WINDOW_SECS} seconds"
            ),
            Self::DeadlineOverflow => write!(formatter, "deadline exceeds the supported range"),
            Self::InvalidDigest => write!(formatter, "digest must be a b3-prefixed BLAKE3 value"),
        }
    }
}

impl Error for FoundationError {}

macro_rules! uuid_identifier {
    ($name:ident, $field:literal) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
        #[serde(transparent)]
        pub struct $name(Uuid);

        impl $name {
            pub const fn from_uuid(value: Uuid) -> Self {
                Self(value)
            }

            pub const fn as_uuid(self) -> Uuid {
                self.0
            }
        }

        impl Display for $name {
            fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
                Display::fmt(&self.0, formatter)
            }
        }

        impl FromStr for $name {
            type Err = FoundationError;

            fn from_str(raw: &str) -> Result<Self, Self::Err> {
                Uuid::parse_str(raw)
                    .map(Self)
                    .map_err(|_| FoundationError::InvalidUuid($field))
            }
        }
    };
}

uuid_identifier!(RequestId, "request_id");
uuid_identifier!(CorrelationId, "correlation_id");
uuid_identifier!(CommandId, "command_id");

fn identity_character(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.' | ':')
}

fn validate_identity(field: &'static str, value: String) -> Result<String, FoundationError> {
    if value.is_empty() {
        return Err(FoundationError::Empty(field));
    }
    if value.len() > MAX_IDENTITY_LENGTH {
        return Err(FoundationError::TooLong {
            field,
            max: MAX_IDENTITY_LENGTH,
        });
    }
    if !value.chars().all(identity_character) {
        return Err(FoundationError::InvalidCharacters(field));
    }
    Ok(value)
}

macro_rules! bounded_identity {
    ($name:ident, $field:literal) => {
        #[derive(Debug, Clone, PartialEq, Eq, Hash)]
        pub struct $name(String);

        impl $name {
            pub fn parse(value: impl Into<String>) -> Result<Self, FoundationError> {
                validate_identity($field, value.into()).map(Self)
            }

            pub fn as_str(&self) -> &str {
                &self.0
            }
        }

        impl Display for $name {
            fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
                formatter.write_str(&self.0)
            }
        }

        impl AsRef<str> for $name {
            fn as_ref(&self) -> &str {
                self.as_str()
            }
        }

        impl FromStr for $name {
            type Err = FoundationError;

            fn from_str(raw: &str) -> Result<Self, Self::Err> {
                Self::parse(raw)
            }
        }

        impl Serialize for $name {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                serializer.serialize_str(&self.0)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let raw = String::deserialize(deserializer)?;
                Self::parse(raw).map_err(<D::Error as serde::de::Error>::custom)
            }
        }
    };
}

bounded_identity!(ConsumerId, "consumer_id");
bounded_identity!(ApplicationId, "application_id");
bounded_identity!(ActorId, "actor_id");

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct IdempotencyKey(String);

impl IdempotencyKey {
    pub fn parse(value: impl Into<String>) -> Result<Self, FoundationError> {
        let value = value.into();
        if value.is_empty() {
            return Err(FoundationError::Empty("idempotency_key"));
        }
        if value.len() > MAX_IDEMPOTENCY_KEY_LENGTH {
            return Err(FoundationError::TooLong {
                field: "idempotency_key",
                max: MAX_IDEMPOTENCY_KEY_LENGTH,
            });
        }
        if !value.chars().all(|character| character.is_ascii_graphic()) {
            return Err(FoundationError::InvalidCharacters("idempotency_key"));
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl Display for IdempotencyKey {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl FromStr for IdempotencyKey {
    type Err = FoundationError;

    fn from_str(raw: &str) -> Result<Self, Self::Err> {
        Self::parse(raw)
    }
}

impl Serialize for IdempotencyKey {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for IdempotencyKey {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = String::deserialize(deserializer)?;
        Self::parse(raw).map_err(<D::Error as serde::de::Error>::custom)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(transparent)]
pub struct DeadlineWindow(u32);

impl DeadlineWindow {
    pub fn new(seconds: u32) -> Result<Self, FoundationError> {
        if !(1..=MAX_DEADLINE_WINDOW_SECS).contains(&seconds) {
            return Err(FoundationError::InvalidDeadlineWindow);
        }
        Ok(Self(seconds))
    }

    pub const fn as_secs(self) -> u32 {
        self.0
    }
}

impl<'de> Deserialize<'de> for DeadlineWindow {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let seconds = u32::deserialize(deserializer)?;
        Self::new(seconds).map_err(<D::Error as serde::de::Error>::custom)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Deadline(u64);

impl Deadline {
    pub const fn from_unix_secs(seconds: u64) -> Self {
        Self(seconds)
    }

    pub fn from_now(now_unix_secs: u64, window: DeadlineWindow) -> Result<Self, FoundationError> {
        now_unix_secs
            .checked_add(u64::from(window.as_secs()))
            .map(Self)
            .ok_or(FoundationError::DeadlineOverflow)
    }

    pub const fn unix_secs(self) -> u64 {
        self.0
    }

    pub const fn is_expired(self, now_unix_secs: u64) -> bool {
        now_unix_secs >= self.0
    }

    pub const fn remaining_secs(self, now_unix_secs: u64) -> u64 {
        self.0.saturating_sub(now_unix_secs)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct DigestDomain(&'static str);

impl DigestDomain {
    pub const fn new(value: &'static str) -> Self {
        Self(value)
    }

    pub const fn as_str(self) -> &'static str {
        self.0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ContentDigest(blake3::Hash);

impl ContentDigest {
    pub fn derive<I, B>(domain: DigestDomain, parts: I) -> Self
    where
        I: IntoIterator<Item = B>,
        B: AsRef<[u8]>,
    {
        let mut hasher = blake3::Hasher::new_derive_key(domain.as_str());
        for part in parts {
            let bytes = part.as_ref();
            hasher.update(&(bytes.len() as u64).to_be_bytes());
            hasher.update(bytes);
        }
        Self(hasher.finalize())
    }

    pub fn as_bytes(&self) -> &[u8; 32] {
        self.0.as_bytes()
    }
}

impl Display for ContentDigest {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "b3:{}", self.0)
    }
}

impl FromStr for ContentDigest {
    type Err = FoundationError;

    fn from_str(raw: &str) -> Result<Self, Self::Err> {
        let hex = raw
            .strip_prefix("b3:")
            .ok_or(FoundationError::InvalidDigest)?;
        blake3::Hash::from_hex(hex)
            .map(Self)
            .map_err(|_| FoundationError::InvalidDigest)
    }
}

impl Serialize for ContentDigest {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for ContentDigest {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = String::deserialize(deserializer)?;
        raw.parse().map_err(<D::Error as serde::de::Error>::custom)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestContext {
    request_id: RequestId,
    correlation_id: CorrelationId,
    consumer_id: Option<ConsumerId>,
    application_id: Option<ApplicationId>,
    actor_id: Option<ActorId>,
    deadline: Option<Deadline>,
}

impl RequestContext {
    pub fn new(
        request_id: RequestId,
        correlation_id: CorrelationId,
        consumer_id: Option<ConsumerId>,
        application_id: Option<ApplicationId>,
        actor_id: Option<ActorId>,
        deadline: Option<Deadline>,
    ) -> Self {
        Self {
            request_id,
            correlation_id,
            consumer_id,
            application_id,
            actor_id,
            deadline,
        }
    }

    pub const fn request_id(&self) -> RequestId {
        self.request_id
    }

    pub const fn correlation_id(&self) -> CorrelationId {
        self.correlation_id
    }

    pub fn consumer_id(&self) -> Option<&ConsumerId> {
        self.consumer_id.as_ref()
    }

    pub fn application_id(&self) -> Option<&ApplicationId> {
        self.application_id.as_ref()
    }

    pub fn actor_id(&self) -> Option<&ActorId> {
        self.actor_id.as_ref()
    }

    pub const fn deadline(&self) -> Option<Deadline> {
        self.deadline
    }
}

#[cfg(test)]
mod tests {
    use super::{
        ApplicationId, CommandId, ContentDigest, CorrelationId, Deadline, DeadlineWindow,
        DigestDomain, IdempotencyKey, RequestContext, RequestId,
    };
    use uuid::Uuid;

    fn uuid(raw: &str) -> Uuid {
        Uuid::parse_str(raw).unwrap()
    }

    #[test]
    fn uuid_identifiers_parse_without_generating_identity_in_foundation() {
        let raw = "98da1dbc-7de7-4bd2-8a5c-e24af5131f38";
        let command: CommandId = raw.parse().unwrap();
        assert_eq!(command.as_uuid(), uuid(raw));
        assert_eq!(command.to_string(), raw);
        assert!("credential=secret".parse::<RequestId>().is_err());
    }

    #[test]
    fn bounded_identifiers_reject_empty_long_and_whitespace_values() {
        assert!(IdempotencyKey::parse("").is_err());
        assert!(IdempotencyKey::parse("contains space").is_err());
        assert!(IdempotencyKey::parse("x".repeat(129)).is_err());
        assert_eq!(
            ApplicationId::parse("control-plane.v1").unwrap().as_str(),
            "control-plane.v1"
        );
    }

    #[test]
    fn deadlines_are_absolute_and_overflow_safe() {
        let window = DeadlineWindow::new(30).unwrap();
        let deadline = Deadline::from_now(100, window).unwrap();
        assert_eq!(deadline.unix_secs(), 130);
        assert_eq!(deadline.remaining_secs(120), 10);
        assert!(deadline.is_expired(130));
        assert!(DeadlineWindow::new(0).is_err());
        assert!(DeadlineWindow::new(86_401).is_err());
    }

    #[test]
    fn content_digests_are_domain_separated_and_length_framed() {
        let first = ContentDigest::derive(
            DigestDomain::new("mobile-proxy.test.v1"),
            [b"ab".as_slice(), b"c"],
        );
        let second = ContentDigest::derive(
            DigestDomain::new("mobile-proxy.test.v1"),
            [b"a".as_slice(), b"bc"],
        );
        let other_domain = ContentDigest::derive(
            DigestDomain::new("mobile-proxy.other.v1"),
            [b"ab".as_slice(), b"c"],
        );
        assert_ne!(first, second);
        assert_ne!(first, other_domain);
        assert_eq!(first.to_string().parse::<ContentDigest>().unwrap(), first);
        assert!(first.to_string().starts_with("b3:"));
    }

    #[test]
    fn request_context_keeps_typed_lineage() {
        let request_id = RequestId::from_uuid(uuid("98da1dbc-7de7-4bd2-8a5c-e24af5131f38"));
        let correlation_id =
            CorrelationId::from_uuid(uuid("4cd306ef-716e-4f76-aef6-679b93bb7770"));
        let context = RequestContext::new(
            request_id,
            correlation_id,
            None,
            Some(ApplicationId::parse("operator-cli").unwrap()),
            None,
            Some(Deadline::from_unix_secs(500)),
        );
        assert_eq!(context.request_id(), request_id);
        assert_eq!(context.correlation_id(), correlation_id);
        assert_eq!(
            context.application_id().map(ApplicationId::as_str),
            Some("operator-cli")
        );
        assert_eq!(context.deadline().map(Deadline::unix_secs), Some(500));
    }
}
