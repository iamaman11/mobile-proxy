use std::fs;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use mobile_proxy_control_plane_sqlite::SqliteStore;
use reqwest::{Client, StatusCode};
use serde_json::Value;
use tokio::time::{sleep, timeout};

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

struct TempDirectory {
    path: PathBuf,
}

impl TempDirectory {
    fn new() -> Self {
        let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-health-process-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).unwrap();
        Self { path }
    }

    fn join(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

struct ChildGuard(Child);

impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn liveness_survives_without_a_phone_and_readiness_tracks_sqlite() {
    let directory = TempDirectory::new();
    let state_path = directory.join("state.sqlite3");
    drop(SqliteStore::open(&state_path).unwrap());

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);

    let child = Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .args([
            "--listen",
            &address.to_string(),
            "--admin-token",
            "admin-secret",
            "--device-token",
            "device-secret",
            "--state-path",
            state_path.to_str().unwrap(),
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let _child = ChildGuard(child);

    let client = Client::builder()
        .timeout(Duration::from_secs(1))
        .build()
        .unwrap();
    let base = format!("http://{address}");

    let live = wait_for_status(&client, &format!("{base}/livez"), StatusCode::OK).await;
    assert_eq!(live["status"], "live");

    let ready = wait_for_status(&client, &format!("{base}/readyz"), StatusCode::OK).await;
    assert_eq!(ready["status"], "ready");
    assert_eq!(
        ready["critical_dependencies"]["durable_store"]["healthy"],
        true
    );
    assert_eq!(ready["device_availability"], "independent");
    let rendered = ready.to_string();
    assert!(!rendered.contains("admin-secret"));
    assert!(!rendered.contains("device-secret"));

    fs::remove_file(&state_path).unwrap();
    let not_ready = wait_for_status(
        &client,
        &format!("{base}/readyz"),
        StatusCode::SERVICE_UNAVAILABLE,
    )
    .await;
    assert_eq!(not_ready["status"], "not_ready");
    assert_eq!(
        not_ready["critical_dependencies"]["durable_store"]["healthy"],
        false
    );
    assert!(!state_path.exists());

    let still_live = wait_for_status(&client, &format!("{base}/livez"), StatusCode::OK).await;
    assert_eq!(still_live["status"], "live");
}

async fn wait_for_status(client: &Client, url: &str, expected: StatusCode) -> Value {
    timeout(Duration::from_secs(5), async {
        loop {
            if let Ok(response) = client.get(url).send().await
                && response.status() == expected
            {
                return response.json().await.unwrap();
            }
            sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap_or_else(|_| panic!("timed out waiting for {expected} from {url}"))
}
