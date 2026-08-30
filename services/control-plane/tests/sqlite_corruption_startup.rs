use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

const ADMIN_TOKEN: &str = "corruption-admin-token";
const DEVICE_TOKEN: &str = "corruption-device-token";
const UI_TOKEN: &str = "corruption-ui-token";

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

struct TempDirectory {
    path: PathBuf,
}

impl TempDirectory {
    fn new() -> Self {
        let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-sqlite-corruption-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).unwrap();
        Self { path }
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

#[test]
fn control_plane_fails_closed_before_readiness_for_corrupt_sqlite_state() {
    let directory = TempDirectory::new();
    let state_path = directory.path.join("control-plane-state.sqlite3");
    fs::write(&state_path, b"not-a-sqlite-database").unwrap();

    let mut child = Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .arg("--listen")
        .arg("127.0.0.1:0")
        .arg("--admin-token")
        .arg(ADMIN_TOKEN)
        .arg("--device-token")
        .arg(DEVICE_TOKEN)
        .arg("--ui-token")
        .arg(UI_TOKEN)
        .arg("--state-path")
        .arg(&state_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();

    for _ in 0..100 {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(!status.success());
            return;
        }
        std::thread::sleep(Duration::from_millis(25));
    }

    child.kill().unwrap();
    child.wait().unwrap();
    panic!("control-plane unexpectedly remained running with corrupt SQLite state");
}
