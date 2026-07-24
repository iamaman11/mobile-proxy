use std::collections::BTreeSet;
use std::error::Error;
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::Path;
use std::time::Duration;

use rusqlite::{Connection, TransactionBehavior, params};

pub const SCHEMA_VERSION: i64 = 1;
pub const BUSY_TIMEOUT: Duration = Duration::from_secs(5);

const EXPECTED_TABLES: [&str; 4] = [
    "command_results",
    "devices",
    "idempotency_claims",
    "pending_commands",
];

const MIGRATION_V1: &str = r#"
CREATE TABLE devices (
    node_id TEXT PRIMARY KEY NOT NULL CHECK (node_id <> ''),
    record_json TEXT NOT NULL CHECK (json_valid(record_json))
) STRICT;

CREATE TABLE command_results (
    scope_key TEXT PRIMARY KEY NOT NULL CHECK (scope_key <> ''),
    command_id TEXT NOT NULL UNIQUE CHECK (command_id <> ''),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    UNIQUE (scope_key, command_id)
) STRICT;

CREATE TABLE idempotency_claims (
    scope_key TEXT PRIMARY KEY NOT NULL CHECK (scope_key <> ''),
    command_id TEXT NOT NULL CHECK (command_id <> ''),
    request_fingerprint TEXT NOT NULL CHECK (request_fingerprint <> ''),
    FOREIGN KEY (scope_key, command_id)
        REFERENCES command_results(scope_key, command_id)
        ON DELETE CASCADE
) STRICT;

CREATE TABLE pending_commands (
    command_id TEXT PRIMARY KEY NOT NULL CHECK (command_id <> ''),
    device_id TEXT NOT NULL CHECK (device_id <> ''),
    queue_position INTEGER NOT NULL CHECK (queue_position >= 0),
    command_json TEXT NOT NULL CHECK (json_valid(command_json)),
    FOREIGN KEY (command_id)
        REFERENCES command_results(command_id)
        ON DELETE RESTRICT,
    UNIQUE (device_id, queue_position)
) STRICT;

CREATE INDEX pending_commands_device_position
    ON pending_commands(device_id, queue_position);
"#;

#[derive(Debug)]
pub enum StoreError {
    Io(std::io::Error),
    Database(rusqlite::Error),
    InvalidValue { field: &'static str },
    UnsupportedSchemaVersion { found: i64, supported: i64 },
    UnexpectedJournalMode,
    UnexpectedForeignKeyState,
    UnexpectedSchema,
}

impl Display for StoreError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(_) => formatter.write_str("SQLite store filesystem operation failed"),
            Self::Database(_) => formatter.write_str("SQLite store operation failed"),
            Self::InvalidValue { field } => write!(formatter, "invalid SQLite field: {field}"),
            Self::UnsupportedSchemaVersion { found, supported } => write!(
                formatter,
                "unsupported SQLite schema version {found}; supported version is {supported}"
            ),
            Self::UnexpectedJournalMode => {
                formatter.write_str("SQLite WAL journal mode could not be established")
            }
            Self::UnexpectedForeignKeyState => {
                formatter.write_str("SQLite foreign-key enforcement could not be established")
            }
            Self::UnexpectedSchema => {
                formatter.write_str("SQLite schema does not match the supported baseline inventory")
            }
        }
    }
}

impl Error for StoreError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Database(error) => Some(error),
            Self::InvalidValue { .. }
            | Self::UnsupportedSchemaVersion { .. }
            | Self::UnexpectedJournalMode
            | Self::UnexpectedForeignKeyState
            | Self::UnexpectedSchema => None,
        }
    }
}

impl From<std::io::Error> for StoreError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<rusqlite::Error> for StoreError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Database(error)
    }
}

pub struct SqliteStore {
    connection: Connection,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InventoryCounts {
    pub devices: i64,
    pub pending_commands: i64,
    pub command_results: i64,
    pub idempotency_claims: i64,
}

impl SqliteStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StoreError> {
        let path = path.as_ref();
        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }

        let connection = Connection::open(path)?;
        Self::initialize(connection, true)
    }

    fn initialize(mut connection: Connection, require_wal: bool) -> Result<Self, StoreError> {
        connection.busy_timeout(BUSY_TIMEOUT)?;
        connection.pragma_update(None, "foreign_keys", true)?;
        connection.pragma_update(None, "synchronous", "FULL")?;

        if require_wal {
            let journal_mode: String =
                connection.query_row("PRAGMA journal_mode = WAL", [], |row| row.get(0))?;
            if !journal_mode.eq_ignore_ascii_case("wal") {
                return Err(StoreError::UnexpectedJournalMode);
            }
        }

        let foreign_keys: i64 =
            connection.query_row("PRAGMA foreign_keys", [], |row| row.get(0))?;
        if foreign_keys != 1 {
            return Err(StoreError::UnexpectedForeignKeyState);
        }

        apply_migrations(&mut connection)?;
        validate_schema(&connection)?;
        Ok(Self { connection })
    }

    pub fn schema_version(&self) -> Result<i64, StoreError> {
        read_schema_version(&self.connection)
    }

    pub fn journal_mode(&self) -> Result<String, StoreError> {
        Ok(self
            .connection
            .query_row("PRAGMA journal_mode", [], |row| row.get(0))?)
    }

    pub fn foreign_keys_enabled(&self) -> Result<bool, StoreError> {
        let enabled: i64 = self
            .connection
            .query_row("PRAGMA foreign_keys", [], |row| row.get(0))?;
        Ok(enabled == 1)
    }

    pub fn busy_timeout_millis(&self) -> Result<i64, StoreError> {
        Ok(self
            .connection
            .query_row("PRAGMA busy_timeout", [], |row| row.get(0))?)
    }

    pub fn inventory_counts(&self) -> Result<InventoryCounts, StoreError> {
        Ok(InventoryCounts {
            devices: table_count(&self.connection, "devices")?,
            pending_commands: table_count(&self.connection, "pending_commands")?,
            command_results: table_count(&self.connection, "command_results")?,
            idempotency_claims: table_count(&self.connection, "idempotency_claims")?,
        })
    }

    pub fn write<T>(
        &mut self,
        operation: impl FnOnce(&WriteTransaction<'_>) -> Result<T, StoreError>,
    ) -> Result<T, StoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let result = {
            let writer = WriteTransaction {
                connection: &transaction,
            };
            operation(&writer)?
        };
        transaction.commit()?;
        Ok(result)
    }

    #[cfg(test)]
    fn open_in_memory() -> Result<Self, StoreError> {
        Self::initialize(Connection::open_in_memory()?, false)
    }
}

pub struct WriteTransaction<'transaction> {
    connection: &'transaction Connection,
}

impl WriteTransaction<'_> {
    pub fn replace_device(&self, node_id: &str, record_json: &str) -> Result<(), StoreError> {
        require_nonempty(node_id, "node_id")?;
        self.connection.execute(
            "INSERT INTO devices (node_id, record_json) VALUES (?1, ?2) \
             ON CONFLICT(node_id) DO UPDATE SET record_json = excluded.record_json",
            params![node_id, record_json],
        )?;
        Ok(())
    }

    pub fn insert_command_result(
        &self,
        scope_key: &str,
        command_id: &str,
        result_json: &str,
    ) -> Result<(), StoreError> {
        require_nonempty(scope_key, "scope_key")?;
        require_nonempty(command_id, "command_id")?;
        self.connection.execute(
            "INSERT INTO command_results (scope_key, command_id, result_json) \
             VALUES (?1, ?2, ?3)",
            params![scope_key, command_id, result_json],
        )?;
        Ok(())
    }

    pub fn insert_idempotency_claim(
        &self,
        scope_key: &str,
        command_id: &str,
        request_fingerprint: &str,
    ) -> Result<(), StoreError> {
        require_nonempty(scope_key, "scope_key")?;
        require_nonempty(command_id, "command_id")?;
        require_nonempty(request_fingerprint, "request_fingerprint")?;
        self.connection.execute(
            "INSERT INTO idempotency_claims (scope_key, command_id, request_fingerprint) \
             VALUES (?1, ?2, ?3)",
            params![scope_key, command_id, request_fingerprint],
        )?;
        Ok(())
    }

    pub fn insert_pending_command(
        &self,
        command_id: &str,
        device_id: &str,
        queue_position: u32,
        command_json: &str,
    ) -> Result<(), StoreError> {
        require_nonempty(command_id, "command_id")?;
        require_nonempty(device_id, "device_id")?;
        self.connection.execute(
            "INSERT INTO pending_commands \
             (command_id, device_id, queue_position, command_json) \
             VALUES (?1, ?2, ?3, ?4)",
            params![command_id, device_id, i64::from(queue_position), command_json],
        )?;
        Ok(())
    }

    pub fn delete_pending_command(&self, command_id: &str) -> Result<bool, StoreError> {
        require_nonempty(command_id, "command_id")?;
        Ok(self.connection.execute(
            "DELETE FROM pending_commands WHERE command_id = ?1",
            params![command_id],
        )? == 1)
    }
}

fn apply_migrations(connection: &mut Connection) -> Result<(), StoreError> {
    let version = read_schema_version(connection)?;
    if version > SCHEMA_VERSION {
        return Err(StoreError::UnsupportedSchemaVersion {
            found: version,
            supported: SCHEMA_VERSION,
        });
    }

    match version {
        0 => {
            let transaction =
                connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            transaction.execute_batch(MIGRATION_V1)?;
            transaction.pragma_update(None, "user_version", SCHEMA_VERSION)?;
            transaction.commit()?;
        }
        SCHEMA_VERSION => {}
        found => {
            return Err(StoreError::UnsupportedSchemaVersion {
                found,
                supported: SCHEMA_VERSION,
            });
        }
    }

    Ok(())
}

fn validate_schema(connection: &Connection) -> Result<(), StoreError> {
    let mut statement = connection.prepare(
        "SELECT name FROM sqlite_schema \
         WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let actual = statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<BTreeSet<_>>>()?;
    let expected = EXPECTED_TABLES
        .into_iter()
        .map(str::to_owned)
        .collect::<BTreeSet<_>>();

    if actual != expected {
        return Err(StoreError::UnexpectedSchema);
    }
    Ok(())
}

fn read_schema_version(connection: &Connection) -> Result<i64, StoreError> {
    Ok(connection.query_row("PRAGMA user_version", [], |row| row.get(0))?)
}

fn table_count(connection: &Connection, table: &str) -> Result<i64, StoreError> {
    let sql = match table {
        "devices" => "SELECT COUNT(*) FROM devices",
        "pending_commands" => "SELECT COUNT(*) FROM pending_commands",
        "command_results" => "SELECT COUNT(*) FROM command_results",
        "idempotency_claims" => "SELECT COUNT(*) FROM idempotency_claims",
        _ => return Err(StoreError::UnexpectedSchema),
    };
    Ok(connection.query_row(sql, [], |row| row.get(0))?)
}

fn require_nonempty(value: &str, field: &'static str) -> Result<(), StoreError> {
    if value.is_empty() {
        return Err(StoreError::InvalidValue { field });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};

    use rusqlite::Connection;

    use super::{
        BUSY_TIMEOUT, InventoryCounts, SCHEMA_VERSION, SqliteStore, StoreError,
    };

    static NEXT_DATABASE_ID: AtomicU64 = AtomicU64::new(1);

    struct TempDatabase {
        path: PathBuf,
    }

    impl TempDatabase {
        fn new(label: &str) -> Self {
            let id = NEXT_DATABASE_ID.fetch_add(1, Ordering::Relaxed);
            Self {
                path: std::env::temp_dir().join(format!(
                    "mobile-proxy-{label}-{}-{id}.sqlite3",
                    std::process::id()
                )),
            }
        }
    }

    impl Drop for TempDatabase {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.path);
            let _ = std::fs::remove_file(sidecar_path(&self.path, "-wal"));
            let _ = std::fs::remove_file(sidecar_path(&self.path, "-shm"));
        }
    }

    fn sidecar_path(path: &Path, suffix: &str) -> PathBuf {
        let mut value = path.as_os_str().to_os_string();
        value.push(suffix);
        PathBuf::from(value)
    }

    #[test]
    fn file_store_applies_required_pragmas_and_v1_schema() {
        let database = TempDatabase::new("sqlite-schema");
        let store = SqliteStore::open(&database.path).unwrap();

        assert_eq!(store.schema_version().unwrap(), SCHEMA_VERSION);
        assert_eq!(store.journal_mode().unwrap().to_ascii_lowercase(), "wal");
        assert!(store.foreign_keys_enabled().unwrap());
        assert_eq!(
            store.busy_timeout_millis().unwrap(),
            BUSY_TIMEOUT.as_millis() as i64
        );
        assert_eq!(
            store.inventory_counts().unwrap(),
            InventoryCounts {
                devices: 0,
                pending_commands: 0,
                command_results: 0,
                idempotency_claims: 0,
            }
        );
    }

    #[test]
    fn migration_is_idempotent_across_reopen() {
        let database = TempDatabase::new("sqlite-reopen");
        let first = SqliteStore::open(&database.path).unwrap();
        assert_eq!(first.schema_version().unwrap(), SCHEMA_VERSION);
        drop(first);

        let second = SqliteStore::open(&database.path).unwrap();
        assert_eq!(second.schema_version().unwrap(), SCHEMA_VERSION);
    }

    #[test]
    fn future_schema_version_fails_closed() {
        let database = TempDatabase::new("sqlite-future-schema");
        let connection = Connection::open(&database.path).unwrap();
        connection
            .pragma_update(None, "user_version", SCHEMA_VERSION + 1)
            .unwrap();
        drop(connection);

        let error = match SqliteStore::open(&database.path) {
            Ok(_) => panic!("future schema unexpectedly opened"),
            Err(error) => error,
        };
        assert!(matches!(
            error,
            StoreError::UnsupportedSchemaVersion {
                found,
                supported
            } if found == SCHEMA_VERSION + 1 && supported == SCHEMA_VERSION
        ));
    }

    #[test]
    fn complete_candidate_commits_atomically_and_survives_reopen() {
        let database = TempDatabase::new("sqlite-commit");
        let mut store = SqliteStore::open(&database.path).unwrap();
        store
            .write(|transaction| {
                transaction.replace_device("device-1", r#"{"node_id":"device-1"}"#)?;
                transaction.insert_command_result(
                    "scope-1",
                    "command-1",
                    r#"{"command_id":"command-1"}"#,
                )?;
                transaction.insert_idempotency_claim(
                    "scope-1",
                    "command-1",
                    "b3:request-fingerprint",
                )?;
                transaction.insert_pending_command(
                    "command-1",
                    "device-1",
                    0,
                    r#"{"command_id":"command-1"}"#,
                )?;
                Ok(())
            })
            .unwrap();

        assert_eq!(
            store.inventory_counts().unwrap(),
            InventoryCounts {
                devices: 1,
                pending_commands: 1,
                command_results: 1,
                idempotency_claims: 1,
            }
        );
        drop(store);

        let reopened = SqliteStore::open(&database.path).unwrap();
        assert_eq!(
            reopened.inventory_counts().unwrap(),
            InventoryCounts {
                devices: 1,
                pending_commands: 1,
                command_results: 1,
                idempotency_claims: 1,
            }
        );
    }

    #[test]
    fn failed_candidate_rolls_back_every_prior_write() {
        let mut store = SqliteStore::open_in_memory().unwrap();
        let result = store.write(|transaction| {
            transaction.replace_device("device-1", r#"{"node_id":"device-1"}"#)?;
            transaction.insert_idempotency_claim(
                "missing-scope",
                "missing-command",
                "b3:request-fingerprint",
            )
        });

        assert!(matches!(result, Err(StoreError::Database(_))));
        assert_eq!(
            store.inventory_counts().unwrap(),
            InventoryCounts {
                devices: 0,
                pending_commands: 0,
                command_results: 0,
                idempotency_claims: 0,
            }
        );
    }

    #[test]
    fn conflicting_replay_evidence_fails_closed_without_replacement() {
        let mut store = SqliteStore::open_in_memory().unwrap();
        store
            .write(|transaction| {
                transaction.insert_command_result(
                    "scope-1",
                    "command-1",
                    r#"{"command_id":"command-1"}"#,
                )?;
                transaction.insert_idempotency_claim(
                    "scope-1",
                    "command-1",
                    "b3:first-request",
                )
            })
            .unwrap();

        let conflict = store.write(|transaction| {
            transaction.insert_command_result(
                "scope-1",
                "command-2",
                r#"{"command_id":"command-2"}"#,
            )
        });
        assert!(matches!(conflict, Err(StoreError::Database(_))));
        assert_eq!(
            store.inventory_counts().unwrap(),
            InventoryCounts {
                devices: 0,
                pending_commands: 0,
                command_results: 1,
                idempotency_claims: 1,
            }
        );
    }

    #[test]
    fn pending_command_deletion_is_part_of_the_same_write_boundary() {
        let mut store = SqliteStore::open_in_memory().unwrap();
        store
            .write(|transaction| {
                transaction.insert_command_result(
                    "scope-1",
                    "command-1",
                    r#"{"command_id":"command-1"}"#,
                )?;
                transaction.insert_pending_command(
                    "command-1",
                    "device-1",
                    0,
                    r#"{"command_id":"command-1"}"#,
                )?;
                assert!(transaction.delete_pending_command("command-1")?);
                Ok(())
            })
            .unwrap();

        assert_eq!(store.inventory_counts().unwrap().pending_commands, 0);
        assert_eq!(store.inventory_counts().unwrap().command_results, 1);
    }
}
