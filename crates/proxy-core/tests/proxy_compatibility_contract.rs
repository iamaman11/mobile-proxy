use std::collections::HashSet;

use proxy_core::proxy_endpoints;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct CompatibilityContract {
    contract_version: u16,
    status: String,
    public_proxy_endpoints: Vec<ContractEndpoint>,
    tunnel_policy: TunnelPolicy,
    compatibility_requirements: CompatibilityRequirements,
}

#[derive(Debug, Deserialize)]
struct ContractEndpoint {
    protocol: String,
    port: u16,
    supports_connect: bool,
    legacy_compatible: bool,
}

#[derive(Debug, Deserialize)]
struct TunnelPolicy {
    primary: String,
    reserve: String,
    reserve_public_port: u16,
    compatibility_transports: Vec<String>,
    plaintext_fallback_allowed: bool,
}

#[derive(Debug, Deserialize)]
struct CompatibilityRequirements {
    preserve_existing_consumers: bool,
    silent_protocol_fallback_allowed: bool,
    silent_transport_downgrade_allowed: bool,
    operator_admin_api_preserved: bool,
    consumer_raw_device_commands_allowed: bool,
}

fn contract() -> CompatibilityContract {
    serde_json::from_str(include_str!(
        "../../../contracts/compatibility/proxy-surface-v1.json"
    ))
    .expect("proxy compatibility contract must be valid JSON")
}

#[test]
fn runtime_proxy_inventory_matches_protected_contract() {
    let contract = contract();
    let declared: Vec<_> = contract
        .public_proxy_endpoints
        .iter()
        .map(|endpoint| (endpoint.protocol.as_str(), endpoint.port))
        .collect();
    let runtime: Vec<_> = proxy_endpoints()
        .iter()
        .map(|endpoint| (endpoint.scheme, endpoint.port))
        .collect();

    assert_eq!(contract.contract_version, 1);
    assert_eq!(contract.status, "protected");
    assert_eq!(runtime, declared);
}

#[test]
fn protected_proxy_endpoints_are_unique_and_connect_capable() {
    let contract = contract();
    let mut protocols = HashSet::new();
    let mut ports = HashSet::new();

    for endpoint in contract.public_proxy_endpoints {
        assert!(protocols.insert(endpoint.protocol));
        assert!(ports.insert(endpoint.port));
        assert!(endpoint.supports_connect);
        assert!(endpoint.legacy_compatible);
    }

    assert_eq!(protocols.len(), 3);
    assert_eq!(ports.len(), 3);
}

#[test]
fn tunnel_policy_remains_quic_first_with_secure_tcp_reserve() {
    let contract = contract();

    assert_eq!(contract.tunnel_policy.primary, "quic");
    assert_eq!(contract.tunnel_policy.reserve, "tls_tcp");
    assert_eq!(contract.tunnel_policy.reserve_public_port, 443);
    assert_eq!(
        contract.tunnel_policy.compatibility_transports,
        ["wireguard"]
    );
    assert!(!contract.tunnel_policy.plaintext_fallback_allowed);
}

#[test]
fn compatibility_policy_is_fail_closed_for_consumers() {
    let requirements = contract().compatibility_requirements;

    assert!(requirements.preserve_existing_consumers);
    assert!(!requirements.silent_protocol_fallback_allowed);
    assert!(!requirements.silent_transport_downgrade_allowed);
    assert!(requirements.operator_admin_api_preserved);
    assert!(!requirements.consumer_raw_device_commands_allowed);
}
