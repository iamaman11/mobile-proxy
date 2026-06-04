pub mod commands;
pub mod constants;
pub mod endpoints;
pub mod records;
pub mod runtime;

pub use commands::{
    CommandAckRequest, DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent,
    RotateAccepted, RotateRequest, default_rotate_request,
};
pub use constants::{
    DEFAULT_AIRPLANE_HOLD_SECS, DEVICE_ID, HTTP_PORT, LOCAL_API, MIXED_PORT, NODE_NAME, RELAY_IP,
    SOCKS5_PORT,
};
pub use endpoints::{ProxyEndpoint, proxy_endpoints};
pub use records::{
    DeviceList, DeviceRecord, HealthRecord, HeartbeatRequest, JobRecord, ProxyRuntimeRecord,
    PublicProbeReport, RegisterDeviceRequest, RuntimeStatusRecord,
};
pub use runtime::{
    Availability, DegradationReasonCode, RuntimeProjection, RuntimeProjectionInput,
    RuntimeReadiness, project_runtime,
};

#[cfg(test)]
mod tests {
    use super::{
        Availability, DEFAULT_AIRPLANE_HOLD_SECS, RuntimeProjectionInput, RuntimeReadiness,
        default_rotate_request, project_runtime, proxy_endpoints,
    };

    #[test]
    fn projection_requires_public_probe_for_ready() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert_eq!(projected.availability, Availability::Degraded.to_string());
    }

    #[test]
    fn projection_rejects_serving_without_cellular_route() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: true,
            current_job: None,
            cellular_route_ready: Some(false),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert!(!projected.serving);
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("cellular_route_missing")
        );
    }

    #[test]
    fn projection_prioritizes_wireguard_readiness_over_proxy_bind() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::WaitingWireguard.to_string(),
            serving: false,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(false),
            local_serving_ready: Some(false),
        });
        assert!(!projected.serving);
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("wireguard_path_not_ready")
        );
    }

    #[test]
    fn projection_rejects_serving_while_rotation_job_exists() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: true,
            current_job: Some(uuid::Uuid::new_v4()),
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert!(!projected.serving);
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("rotation_in_progress")
        );
    }

    #[test]
    fn proxy_endpoints_have_expected_public_ports() {
        let endpoints = proxy_endpoints();
        assert_eq!(endpoints[0].port, 1080);
        assert_eq!(endpoints[1].port, 1081);
        assert_eq!(endpoints[2].port, 3128);
    }

    #[test]
    fn default_rotate_request_uses_default_airplane_hold() {
        let request = default_rotate_request();
        assert_eq!(request.hold_secs, Some(DEFAULT_AIRPLANE_HOLD_SECS));
    }
}
