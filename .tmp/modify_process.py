from pathlib import Path

p = Path.cwd() / "services/control-plane/tests/sqlite_backend_process_acceptance.rs"
s = p.read_text()
old = '''impl Daemon {
    async fn start(backend: Option<&str>, state_path: &Path, client: &Client) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);

        let mut process = Command::new(control_plane_binary());
        process
            .arg("--listen")
            .arg(address.to_string())
            .arg("--admin-token")
            .arg(ADMIN_TOKEN)
            .arg("--device-token")
            .arg(DEVICE_TOKEN);
        if let Some(backend) = backend {
            process.arg("--state-backend").arg(backend);
        }
        let child = process
            .arg("--state-path")
'''
new = '''impl Daemon {
    async fn start(state_path: &Path, client: &Client) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);

        let child = Command::new(control_plane_binary())
            .arg("--listen")
            .arg(address.to_string())
            .arg("--admin-token")
            .arg(ADMIN_TOKEN)
            .arg("--device-token")
            .arg(DEVICE_TOKEN)
            .arg("--state-path")
'''
if old not in s:
    raise SystemExit("daemon block not found")
s = s.replace(old, new)
s = s.replace("Daemon::start(None, &sqlite, &client)", "Daemon::start(&sqlite, &client)")
s = s.replace(
    "async fn sqlite_default_restart_and_current_state_json_rollback_work_through_real_daemon()",
    "async fn sqlite_only_restart_and_previous_release_rollback_artifact_round_trip()",
)
s = s.replace(
    '    let rollback_json = directory.join("control-plane-state-rollback.json");',
    '    let rollback_json = directory.join("control-plane-state-rollback.json");\n'
    '    let rollback_sqlite = directory.join("control-plane-state-rollback.sqlite3");\n'
    '    let rollback_diagnostic = directory.join("control-plane-state-rollback-diagnostic.json");',
)
old_block = '''    {
        let mut rollback = Daemon::start(Some("json"), &rollback_json, &client).await;
        let devices = list_devices(&client, &rollback).await;
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].node_id, DEVICE_ID);
        assert_eq!(next_command(&client, &rollback).await, None);

        let replayed: DeviceCommand =
            replay_command(&client, &rollback, DesiredState::HealthyServing)
                .await
                .error_for_status()
                .unwrap()
                .json()
                .await
                .unwrap();
        assert_eq!(replayed, original_command);

        let conflict = replay_command(&client, &rollback, DesiredState::DegradedSafe).await;
        assert_eq!(conflict.status(), StatusCode::CONFLICT);
        rollback.stop();
    }

    assert_eq!(fs::read(&rollback_json).unwrap(), rollback_bytes);
'''
new_block = '''    let rollback_import = run_import(&rollback_json, &rollback_sqlite, &rollback_diagnostic);
    assert!(
        rollback_import.status.success(),
        "previous-release rollback artifact failed round-trip import: {}",
        String::from_utf8_lossy(&rollback_import.stderr)
    );
    assert!(rollback_diagnostic.is_file());

    {
        let mut round_trip = Daemon::start(&rollback_sqlite, &client).await;
        let devices = list_devices(&client, &round_trip).await;
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].node_id, DEVICE_ID);
        assert_eq!(next_command(&client, &round_trip).await, None);

        let replayed: DeviceCommand =
            replay_command(&client, &round_trip, DesiredState::HealthyServing)
                .await
                .error_for_status()
                .unwrap()
                .json()
                .await
                .unwrap();
        assert_eq!(replayed, original_command);

        let conflict = replay_command(&client, &round_trip, DesiredState::DegradedSafe).await;
        assert_eq!(conflict.status(), StatusCode::CONFLICT);
        round_trip.stop();
    }

    assert_eq!(fs::read(&rollback_json).unwrap(), rollback_bytes);
'''
if old_block not in s:
    raise SystemExit("rollback daemon block not found")
s = s.replace(old_block, new_block)

anchor = '''#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sqlite_only_restart_and_previous_release_rollback_artifact_round_trip() {
'''
retired = '''#[test]
fn retired_state_backend_option_is_rejected_before_state_access() {
    let directory = TempDirectory::new("retired-backend");
    let missing = directory.join("must-not-be-created.sqlite3");
    let output = Command::new(control_plane_binary())
        .arg("--admin-token")
        .arg(ADMIN_TOKEN)
        .arg("--device-token")
        .arg(DEVICE_TOKEN)
        .arg("--state-backend")
        .arg("json")
        .arg("--state-path")
        .arg(&missing)
        .output()
        .unwrap();

    assert!(!output.status.success());
    assert!(!missing.exists());
    assert!(String::from_utf8_lossy(&output.stderr).contains("unexpected argument '--state-backend'"));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sqlite_only_restart_and_previous_release_rollback_artifact_round_trip() {
'''
if anchor not in s:
    raise SystemExit("test anchor not found")
s = s.replace(anchor, retired)
p.write_text(s)
