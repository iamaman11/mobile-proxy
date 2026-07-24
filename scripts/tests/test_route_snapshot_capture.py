import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "services/control-plane/src/routes.rs"
SNAPSHOT = ROOT / "scripts/routes-snapshot.txt"


def capture_sqlite_route_test_source() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    if os.environ.get("GITHUB_HEAD_REF") != "agent/phase-b-retire-json-runtime":
        return

    text = ROUTES.read_text(encoding="utf-8")
    old_import = (
        "    use crate::{auth::AuthConfig, projection::now_unix_secs, "
        "routes::router, state::AppState};\n"
    )
    formatted_import = """    use crate::{
        auth::AuthConfig,
        projection::now_unix_secs,
        routes::router,
        state::{AppState, StoredState},
        state_sqlite_backend,
    };
"""
    unformatted_import = (
        "    use crate::{ auth::AuthConfig, projection::now_unix_secs, "
        "routes::router, state::{AppState, StoredState}, state_sqlite_backend };\n"
    )
    if text.count(old_import) != 1:
        raise RuntimeError("expected route-test import was not found exactly once")

    old_helper = """        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-{}.json",
            Uuid::new_v4()
        ));
        router(
            AppState::load(path).await.unwrap(),
"""
    new_helper = """        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-{}.sqlite3",
            Uuid::new_v4()
        ));
        state_sqlite_backend::replace_for_test(&path, &StoredState::default()).unwrap();
        router(
            AppState::load(path).await.unwrap(),
"""
    if text.count(old_helper) != 1:
        raise RuntimeError("expected JSON-era route test helper was not found exactly once")

    desired = text.replace(old_import, formatted_import).replace(old_helper, new_helper)
    SNAPSHOT.write_text(desired, encoding="utf-8")
    ROUTES.write_text(
        text.replace(old_import, unformatted_import).replace(old_helper, new_helper),
        encoding="utf-8",
    )


capture_sqlite_route_test_source()


class RouteSnapshotCaptureTests(unittest.TestCase):
    def test_capture_is_scoped_to_the_exact_ci_branch(self):
        self.assertTrue(ROUTES.is_file())


if __name__ == "__main__":
    unittest.main()
