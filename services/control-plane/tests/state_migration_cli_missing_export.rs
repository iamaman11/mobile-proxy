use std::fs;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

fn migration_binary() -> &'static str {
    env!("CARGO_BIN_EXE_control-plane-state-migrate")
}

#[test]
fn missing_export_source_fails_without_creating_database_or_diagnostic() {
    let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
    let directory = std::env::temp_dir().join(format!(
        "mobile-proxy-state-export-missing-{}-{id}",
        std::process::id()
    ));
    fs::create_dir_all(&directory).unwrap();
    let sqlite = directory.join("missing.sqlite3");
    let diagnostic = directory.join("diagnostic.json");

    let output = Command::new(migration_binary())
        .args([
            "export",
            "--sqlite",
            sqlite.to_str().unwrap(),
            "--diagnostic-json",
            diagnostic.to_str().unwrap(),
        ])
        .output()
        .unwrap();

    assert!(!output.status.success());
    assert!(!sqlite.exists());
    assert!(!diagnostic.exists());
    let _ = fs::remove_dir_all(&directory);
}
