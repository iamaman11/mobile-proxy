use std::path::{Path, PathBuf};

use axum::{Json, Router, extract::State, http::StatusCode, response::IntoResponse, routing::get};
use mobile_proxy_control_plane_sqlite::SqliteStore;
use serde_json::{Value, json};

pub fn router(state_path: PathBuf) -> Router {
    Router::new()
        .route("/livez", get(liveness))
        .route("/readyz", get(readiness))
        .with_state(state_path)
}

async fn liveness() -> Json<Value> {
    Json(json!({
        "status": "live"
    }))
}

async fn readiness(State(state_path): State<PathBuf>) -> impl IntoResponse {
    let healthy = tokio::task::spawn_blocking(move || durable_store_ready(&state_path))
        .await
        .unwrap_or(false);
    let status = if healthy {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    let body = Json(json!({
        "status": if healthy { "ready" } else { "not_ready" },
        "critical_dependencies": {
            "durable_store": {
                "backend": "sqlite",
                "healthy": healthy
            }
        },
        "device_availability": "independent"
    }));
    (status, body)
}

fn durable_store_ready(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Ok(mut store) = SqliteStore::open_existing(path) else {
        return false;
    };
    store.load_snapshot().is_ok()
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    use mobile_proxy_control_plane_sqlite::SqliteStore;

    use super::durable_store_ready;

    static NEXT_ID: AtomicU64 = AtomicU64::new(1);

    #[test]
    fn durable_store_check_never_creates_a_missing_database() {
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-health-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("state.sqlite3");

        assert!(!durable_store_ready(&path));
        assert!(!path.exists());

        drop(SqliteStore::open(&path).unwrap());
        assert!(durable_store_ready(&path));

        fs::remove_file(&path).unwrap();
        assert!(!durable_store_ready(&path));
        assert!(!path.exists());
        let _ = fs::remove_dir_all(directory);
    }
}
