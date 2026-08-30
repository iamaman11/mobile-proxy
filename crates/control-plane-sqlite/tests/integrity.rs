use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_control_plane_sqlite::{SqliteStore, StoreError};
use rusqlite::Connection;

static NEXT_DATABASE_ID: AtomicU64 = AtomicU64::new(1);

struct TempDatabase {
    path: PathBuf,
}

impl TempDatabase {
    fn new() -> Self {
        let id = NEXT_DATABASE_ID.fetch_add(1, Ordering::Relaxed);
        Self {
            path: std::env::temp_dir().join(format!(
                "mobile-proxy-integrity-{}-{id}.sqlite3",
                std::process::id()
            )),
        }
    }
}

impl Drop for TempDatabase {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
        let _ = std::fs::remove_file(format!("{}-wal", self.path.display()));
        let _ = std::fs::remove_file(format!("{}-shm", self.path.display()));
    }
}

#[test]
fn existing_database_with_check_constraint_corruption_fails_integrity_validation() {
    let database = TempDatabase::new();
    let store = SqliteStore::open(&database.path).unwrap();
    drop(store);

    let connection = Connection::open(&database.path).unwrap();
    connection
        .pragma_update(None, "ignore_check_constraints", true)
        .unwrap();
    connection
        .execute(
            "INSERT INTO devices (node_id, record_json) VALUES ('', '{}')",
            [],
        )
        .unwrap();
    drop(connection);

    let error = match SqliteStore::open_existing(&database.path) {
        Ok(_) => panic!("corrupt SQLite state unexpectedly opened"),
        Err(error) => error,
    };
    assert!(matches!(error, StoreError::IntegrityCheckFailed));
}
