from pathlib import Path
import subprocess


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    file.write_text(text.replace(old, new, 1))


projection = "services/control-plane/src/projection.rs"
replace_once(
    projection,
    "pub fn build_registered_device(req: RegisterDeviceRequest) -> DeviceRecord {",
    '''const TUNNEL_ACTIVE_TRANSPORTS: &[&str] = &["tcp", "quic", "tls_tcp"];
const TUNNEL_FRESHNESS_VALUES: &[&str] = &["unknown", "fresh", "stale"];
const TUNNEL_FAILOVER_REASONS: &[&str] = &[
    "connect_timeout",
    "connect_failed",
    "authentication_failed",
    "session_closed",
    "session_error",
];

fn normalize_tunnel_observability(
    connected: Option<bool>,
    active_transport: Option<String>,
    freshness: Option<String>,
    failover_reason: Option<String>,
) -> (Option<String>, Option<String>, Option<String>) {
    let freshness = bounded_tunnel_value(freshness, TUNNEL_FRESHNESS_VALUES);
    let active_transport = bounded_tunnel_value(active_transport, TUNNEL_ACTIVE_TRANSPORTS);
    let active_transport = if connected == Some(true) && freshness.as_deref() == Some("fresh") {
        active_transport
    } else {
        None
    };
    let failover_reason = bounded_tunnel_value(failover_reason, TUNNEL_FAILOVER_REASONS);
    (active_transport, freshness, failover_reason)
}

fn bounded_tunnel_value(value: Option<String>, allowed: &[&str]) -> Option<String> {
    value.filter(|candidate| allowed.contains(&candidate.as_str()))
}

pub fn build_registered_device(req: RegisterDeviceRequest) -> DeviceRecord {''',
)
replace_once(
    projection,
    '''    let now = now_unix_secs();

    DeviceRecord {
''',
    '''    let now = now_unix_secs();
    let (
        reverse_tunnel_active_transport,
        reverse_tunnel_freshness,
        reverse_tunnel_failover_reason,
    ) = normalize_tunnel_observability(
        req.reverse_tunnel_connected,
        req.reverse_tunnel_active_transport,
        req.reverse_tunnel_freshness,
        req.reverse_tunnel_failover_reason,
    );

    DeviceRecord {
''',
)
replace_once(
    projection,
    '''        reverse_tunnel_active_transport: req.reverse_tunnel_active_transport,
        reverse_tunnel_freshness: req.reverse_tunnel_freshness,
        reverse_tunnel_failover_reason: req.reverse_tunnel_failover_reason,
''',
    '''        reverse_tunnel_active_transport,
        reverse_tunnel_freshness,
        reverse_tunnel_failover_reason,
''',
)
replace_once(
    projection,
    "pub fn now_unix_secs() -> String {",
    '''#[cfg(test)]
mod tests {
    use super::normalize_tunnel_observability;

    #[test]
    fn tunnel_observability_is_allowlisted_and_consistent() {
        let normalized = normalize_tunnel_observability(
            Some(true),
            Some("tls_tcp".into()),
            Some("fresh".into()),
            Some("connect_timeout".into()),
        );
        assert_eq!(normalized.0.as_deref(), Some("tls_tcp"));
        assert_eq!(normalized.1.as_deref(), Some("fresh"));
        assert_eq!(normalized.2.as_deref(), Some("connect_timeout"));

        let invalid = normalize_tunnel_observability(
            Some(true),
            Some("credential=secret".into()),
            Some("arbitrary".into()),
            Some("raw-provider-error".into()),
        );
        assert_eq!(invalid, (None, None, None));

        let stale = normalize_tunnel_observability(
            Some(false),
            Some("quic".into()),
            Some("stale".into()),
            Some("session_closed".into()),
        );
        assert_eq!(stale.0, None);
        assert_eq!(stale.1.as_deref(), Some("stale"));
        assert_eq!(stale.2.as_deref(), Some("session_closed"));
    }
}

pub fn now_unix_secs() -> String {''',
)
workflow = subprocess.check_output(
    ["git", "show", "origin/main:.github/workflows/rust-quality.yml"],
    text=True,
)
Path(".github/workflows/rust-quality.yml").write_text(workflow)
Path(__file__).unlink()
