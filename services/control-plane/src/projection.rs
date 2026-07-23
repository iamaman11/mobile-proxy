use std::time::{SystemTime, UNIX_EPOCH};

use proxy_core::{
    DeviceRecord, HeartbeatRequest, PublicProbeReport, RegisterDeviceRequest,
    RuntimeProjectionInput, project_runtime,
};

const TUNNEL_ACTIVE_TRANSPORTS: &[&str] = &["tcp", "quic", "tls_tcp"];
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

pub fn build_registered_device(req: RegisterDeviceRequest) -> DeviceRecord {
    let projection = project_runtime(RuntimeProjectionInput {
        readiness_state: "booting".into(),
        serving: false,
        publicly_serving: false,
        current_job: None,
        cellular_route_ready: None,
        proxy_bind_ready: None,
        local_serving_ready: None,
    });

    DeviceRecord {
        node_id: req.node_id,
        node_name: req.node_name,
        readiness_state: projection.readiness_state,
        serving: projection.serving,
        proxy_status: req.proxy_status,
        proxy_pid: None,
        last_public_ip: None,
        current_job: None,
        last_proxy_error: None,
        version: None,
        config_fingerprint: None,
        binary_fingerprint: None,
        active_operator_profile: None,
        active_operator_plmn: None,
        publicly_serving: false,
        public_probe_error: None,
        public_probe_at: None,
        cellular_route_ready: None,
        proxy_bind_ready: None,
        local_serving_ready: None,
        tun0_present: None,
        wg_handshake_recent: None,
        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        reverse_tunnel_active_transport: None,
        reverse_tunnel_freshness: None,
        reverse_tunnel_failover_reason: None,
        tunnel_owner: req.tunnel_owner,
        last_heartbeat_at: None,
        availability: projection.availability,
        degradation_reason_code: projection.degradation_reason_code,
        serving_failure_reason: projection.serving_failure_reason,
        desired_state: Some("degraded_safe".into()),
        recovery_intent: Some("none".into()),
        last_event_at: Some(now_unix_secs()),
    }
}

pub fn build_heartbeat_device(
    req: HeartbeatRequest,
    publicly_serving: bool,
    public_probe_error: Option<String>,
    public_probe_at: Option<String>,
) -> DeviceRecord {
    let projection = project_runtime(RuntimeProjectionInput {
        readiness_state: req.readiness_state,
        serving: req.serving,
        publicly_serving,
        current_job: req.current_job,
        cellular_route_ready: req.cellular_route_ready,
        proxy_bind_ready: req.proxy_bind_ready,
        local_serving_ready: req.local_serving_ready,
    });
    let now = now_unix_secs();
    let (reverse_tunnel_active_transport, reverse_tunnel_freshness, reverse_tunnel_failover_reason) =
        normalize_tunnel_observability(
            req.reverse_tunnel_connected,
            req.reverse_tunnel_active_transport,
            req.reverse_tunnel_freshness,
            req.reverse_tunnel_failover_reason,
        );

    DeviceRecord {
        node_id: req.node_id,
        node_name: req.node_name,
        readiness_state: projection.readiness_state,
        serving: projection.serving,
        proxy_status: req.proxy_status,
        proxy_pid: req.proxy_pid,
        last_public_ip: req.last_public_ip,
        current_job: req.current_job,
        last_proxy_error: req.last_proxy_error,
        version: req.version,
        config_fingerprint: req.config_fingerprint,
        binary_fingerprint: req.binary_fingerprint,
        active_operator_profile: req.active_operator_profile,
        active_operator_plmn: req.active_operator_plmn,
        publicly_serving,
        public_probe_error,
        public_probe_at,
        cellular_route_ready: req.cellular_route_ready,
        proxy_bind_ready: req.proxy_bind_ready,
        local_serving_ready: req.local_serving_ready,
        tun0_present: req.tun0_present,
        wg_handshake_recent: req.wg_handshake_recent,
        reverse_tunnel_connected: req.reverse_tunnel_connected,
        reverse_tunnel_last_error: req.reverse_tunnel_last_error,
        reverse_tunnel_active_transport,
        reverse_tunnel_freshness,
        reverse_tunnel_failover_reason,
        tunnel_owner: req.tunnel_owner,
        last_heartbeat_at: Some(now.clone()),
        availability: projection.availability,
        degradation_reason_code: projection.degradation_reason_code,
        serving_failure_reason: projection.serving_failure_reason,
        desired_state: Some("healthy_serving".into()),
        recovery_intent: Some("none".into()),
        last_event_at: Some(now),
    }
}

pub fn apply_public_probe(device: &mut DeviceRecord, req: PublicProbeReport) {
    device.publicly_serving = req.publicly_serving;
    device.public_probe_error = req.public_probe_error;
    device.public_probe_at = Some(now_unix_secs());
    let projection = project_runtime(RuntimeProjectionInput {
        readiness_state: device.readiness_state.clone(),
        serving: device.serving,
        publicly_serving: device.publicly_serving,
        current_job: device.current_job,
        cellular_route_ready: device.cellular_route_ready,
        proxy_bind_ready: device.proxy_bind_ready,
        local_serving_ready: device.local_serving_ready,
    });
    device.readiness_state = projection.readiness_state;
    device.serving = projection.serving;
    device.availability = projection.availability;
    device.degradation_reason_code = projection.degradation_reason_code;
    device.serving_failure_reason = projection.serving_failure_reason;
    device.last_event_at = Some(now_unix_secs());
}

pub fn now_unix_secs() -> String {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_secs().to_string(),
        Err(_) => "0".into(),
    }
}

#[cfg(test)]
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
