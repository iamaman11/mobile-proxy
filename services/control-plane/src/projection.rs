use std::time::{SystemTime, UNIX_EPOCH};

use proxy_core::{
    DeviceRecord, HeartbeatRequest, PublicProbeReport, RegisterDeviceRequest,
    RuntimeProjectionInput, project_runtime,
};

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
    device.public_probe_at = Some(req.public_probe_at);
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
