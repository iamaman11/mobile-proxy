use proxy_core::{
    Generation, LifecycleScope, ObservedVm, OwnershipMetadata, OwnershipObservation, PlannedCreate,
    ProviderResourceId, VerifiedMutationTarget,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::fmt;
use uuid::Uuid;

const TAG_PROJECT: &str = "mobile-proxy:project=";
const TAG_MANAGER: &str = "mobile-proxy:managed-by=";
const TAG_SCOPE: &str = "mobile-proxy:scope=";
const TAG_INTENT: &str = "mobile-proxy:intent=";
const TAG_GENERATION: &str = "mobile-proxy:generation=";

pub const ITEM18_LIVE_PROVIDER_MUTATION_ALLOWED: bool = false;
pub const ITEM18_FINAL_PRODUCTION_AUTHORITY_ALLOWED: bool = false;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VultrMethod {
    Get,
    Post,
    Patch,
    Delete,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VultrRequest {
    pub method: VultrMethod,
    pub path: String,
    pub body: Option<Value>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct VultrVmSpec {
    pub region: String,
    pub plan: String,
    pub os_id: u64,
    pub label: String,
}

impl VultrVmSpec {
    pub fn fingerprint(&self) -> String {
        format!(
            "vultr:{}:{}:{}:{}",
            self.region, self.plan, self.os_id, self.label
        )
    }
}

#[derive(Clone, Debug, Deserialize)]
pub struct VultrInstanceDto {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub tags: Vec<String>,
    pub region: String,
    pub plan: String,
    pub os_id: u64,
}

#[derive(Clone, Debug, Deserialize)]
struct VultrInstancesDto {
    instances: Vec<VultrInstanceDto>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VultrAdapterError {
    InvalidProviderUuid,
    InvalidOwnershipMetadata,
    InvalidResponse,
    Item18LiveMutationForbidden,
    FinalProductionAuthorityForbidden,
}

impl fmt::Display for VultrAdapterError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::InvalidProviderUuid => "Vultr instance ID is not a valid immutable UUID",
            Self::InvalidOwnershipMetadata => "Vultr ownership tags are invalid",
            Self::InvalidResponse => "Vultr response does not match the typed adapter contract",
            Self::Item18LiveMutationForbidden => "item 18 forbids live Vultr lifecycle execution",
            Self::FinalProductionAuthorityForbidden => "item 18 forbids final production authority",
        })
    }
}

impl std::error::Error for VultrAdapterError {}

pub struct VultrLifecycleAdapter;

impl VultrLifecycleAdapter {
    pub fn list_instances_request() -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Get,
            path: "/v2/instances".to_owned(),
            body: None,
        }
    }

    pub fn decode_instances(body: &[u8]) -> Result<Vec<ObservedVm>, VultrAdapterError> {
        let response: VultrInstancesDto =
            serde_json::from_slice(body).map_err(|_| VultrAdapterError::InvalidResponse)?;
        response
            .instances
            .into_iter()
            .map(Self::decode_instance)
            .collect()
    }

    pub fn decode_instance(instance: VultrInstanceDto) -> Result<ObservedVm, VultrAdapterError> {
        let provider_uuid =
            Uuid::parse_str(&instance.id).map_err(|_| VultrAdapterError::InvalidProviderUuid)?;
        let provider_id = ProviderResourceId::new(provider_uuid.to_string())
            .map_err(|_| VultrAdapterError::InvalidProviderUuid)?;
        let ownership = decode_ownership(&instance.tags)?;
        let spec_fingerprint = VultrVmSpec {
            region: instance.region,
            plan: instance.plan,
            os_id: instance.os_id,
            label: instance.label.clone(),
        }
        .fingerprint();

        Ok(ObservedVm {
            provider_id,
            display_name: instance.label,
            ownership,
            spec_fingerprint,
        })
    }

    pub fn create_request(plan: &PlannedCreate, spec: &VultrVmSpec) -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Post,
            path: "/v2/instances".to_owned(),
            body: Some(json!({
                "region": spec.region,
                "plan": spec.plan,
                "os_id": spec.os_id,
                "label": spec.label,
                "tags": encode_ownership(&plan.ownership()),
            })),
        }
    }

    pub fn stop_request(target: &VerifiedMutationTarget) -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Post,
            path: "/v2/instances/halt".to_owned(),
            body: Some(json!({
                "instance_ids": [target.provider_id().as_str()],
            })),
        }
    }

    pub fn reconfigure_request(target: &VerifiedMutationTarget, label: &str) -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Patch,
            path: format!("/v2/instances/{}", target.provider_id().as_str()),
            body: Some(json!({
                "label": label,
                "tags": encode_ownership(&target.expected_ownership()),
            })),
        }
    }

    pub fn snapshot_request(target: &VerifiedMutationTarget) -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Post,
            path: "/v2/snapshots".to_owned(),
            body: Some(json!({
                "instance_id": target.provider_id().as_str(),
                "description": format!(
                    "mobile-proxy-{}-g{}",
                    target.intent().scope().as_str(),
                    target.generation().get()
                ),
            })),
        }
    }

    pub fn delete_request(target: &VerifiedMutationTarget) -> VultrRequest {
        VultrRequest {
            method: VultrMethod::Delete,
            path: format!("/v2/instances/{}", target.provider_id().as_str()),
            body: None,
        }
    }

    pub fn replacement_create_request(
        target: &VerifiedMutationTarget,
        spec: &VultrVmSpec,
    ) -> Result<VultrRequest, VultrAdapterError> {
        let generation = target
            .generation()
            .next()
            .map_err(|_| VultrAdapterError::InvalidOwnershipMetadata)?;
        let ownership = OwnershipMetadata::exact(target.intent(), generation);
        Ok(VultrRequest {
            method: VultrMethod::Post,
            path: "/v2/instances".to_owned(),
            body: Some(json!({
                "region": spec.region,
                "plan": spec.plan,
                "os_id": spec.os_id,
                "label": spec.label,
                "tags": encode_ownership(&ownership),
            })),
        })
    }

    pub fn enforce_item18_live_boundary(
        scope: LifecycleScope,
        mutation_requested: bool,
    ) -> Result<(), VultrAdapterError> {
        if scope == LifecycleScope::Production {
            return Err(VultrAdapterError::FinalProductionAuthorityForbidden);
        }
        if mutation_requested {
            return Err(VultrAdapterError::Item18LiveMutationForbidden);
        }
        Ok(())
    }
}

pub fn encode_ownership(metadata: &OwnershipMetadata) -> Vec<String> {
    vec![
        format!("{TAG_PROJECT}{}", metadata.project),
        format!("{TAG_MANAGER}{}", metadata.managed_by),
        format!("{TAG_SCOPE}{}", metadata.scope.as_str()),
        format!("{TAG_INTENT}{}", metadata.intent_id),
        format!("{TAG_GENERATION}{}", metadata.generation.get()),
    ]
}

pub fn decode_ownership(tags: &[String]) -> Result<OwnershipObservation, VultrAdapterError> {
    let project = exact_tag_value(tags, TAG_PROJECT)?;
    let managed_by = exact_tag_value(tags, TAG_MANAGER)?;
    let scope = exact_tag_value(tags, TAG_SCOPE)?;
    let intent_id = exact_tag_value(tags, TAG_INTENT)?;
    let generation = exact_tag_value(tags, TAG_GENERATION)?;

    let present = [
        project.is_some(),
        managed_by.is_some(),
        scope.is_some(),
        intent_id.is_some(),
        generation.is_some(),
    ];
    if present.iter().all(|value| !value) {
        return Ok(OwnershipObservation::Missing);
    }
    if present.iter().any(|value| !value) {
        return Ok(OwnershipObservation::Conflicting);
    }

    let scope = match scope.expect("checked above") {
        "acceptance" => LifecycleScope::Acceptance,
        "production" => LifecycleScope::Production,
        _ => return Ok(OwnershipObservation::Conflicting),
    };
    let generation = generation
        .expect("checked above")
        .parse::<u64>()
        .ok()
        .and_then(|value| Generation::new(value).ok());
    let Some(generation) = generation else {
        return Ok(OwnershipObservation::Conflicting);
    };

    Ok(OwnershipObservation::Exact(OwnershipMetadata {
        project: project.expect("checked above").to_owned(),
        managed_by: managed_by.expect("checked above").to_owned(),
        scope,
        intent_id: intent_id.expect("checked above").to_owned(),
        generation,
    }))
}

fn exact_tag_value<'a>(
    tags: &'a [String],
    prefix: &str,
) -> Result<Option<&'a str>, VultrAdapterError> {
    let mut matches = tags.iter().filter_map(|tag| tag.strip_prefix(prefix));
    let first = matches.next();
    if matches.next().is_some() {
        return Err(VultrAdapterError::InvalidOwnershipMetadata);
    }
    Ok(first)
}

#[cfg(test)]
mod tests {
    use super::*;
    use proxy_core::{
        DesiredVm, LifecycleError, OwnershipIntent, ReconcilePlan, VmBinding, authorize_mutation,
        plan_present,
    };

    fn intent() -> OwnershipIntent {
        OwnershipIntent::new(LifecycleScope::Acceptance, "candidate:0123456789abcdef").unwrap()
    }

    fn spec() -> VultrVmSpec {
        VultrVmSpec {
            region: "waw".to_owned(),
            plan: "vc2-1c-2gb".to_owned(),
            os_id: 2284,
            label: "mobile-proxy-acceptance".to_owned(),
        }
    }

    fn dto(id: &str, tags: Vec<String>) -> VultrInstanceDto {
        let spec = spec();
        VultrInstanceDto {
            id: id.to_owned(),
            label: spec.label,
            tags,
            region: spec.region,
            plan: spec.plan,
            os_id: spec.os_id,
        }
    }

    fn verified_target() -> VerifiedMutationTarget {
        let generation = Generation::new(4).unwrap();
        let metadata = OwnershipMetadata::exact(&intent(), generation);
        let observed = VultrLifecycleAdapter::decode_instance(dto(
            "11111111-1111-4111-8111-111111111111",
            encode_ownership(&metadata),
        ))
        .unwrap();
        let binding = VmBinding {
            intent: intent(),
            provider_id: observed.provider_id.clone(),
            generation,
        };
        authorize_mutation(
            &binding,
            &[observed],
            generation,
            proxy_core::MutationKind::Delete,
        )
        .unwrap()
    }

    #[test]
    fn exact_tags_round_trip_without_fuzzy_matching() {
        let metadata = OwnershipMetadata::exact(&intent(), Generation::new(9).unwrap());
        assert_eq!(
            decode_ownership(&encode_ownership(&metadata)).unwrap(),
            OwnershipObservation::Exact(metadata)
        );
    }

    #[test]
    fn duplicate_ownership_key_is_conflicting_and_rejected() {
        let metadata = OwnershipMetadata::exact(&intent(), Generation::new(9).unwrap());
        let mut tags = encode_ownership(&metadata);
        tags.push("mobile-proxy:intent=other".to_owned());
        assert_eq!(
            decode_ownership(&tags),
            Err(VultrAdapterError::InvalidOwnershipMetadata)
        );
    }

    #[test]
    fn partial_ownership_tags_are_conflicting() {
        assert_eq!(
            decode_ownership(&["mobile-proxy:project=mobile-proxy".to_owned()]).unwrap(),
            OwnershipObservation::Conflicting
        );
    }

    #[test]
    fn provider_identity_must_be_a_vultr_uuid() {
        assert_eq!(
            VultrLifecycleAdapter::decode_instance(dto("not-a-uuid", vec![])),
            Err(VultrAdapterError::InvalidProviderUuid)
        );
    }

    #[test]
    fn create_request_comes_only_from_clean_provider_neutral_plan() {
        let desired = DesiredVm {
            intent: intent(),
            display_name: spec().label.clone(),
            spec_fingerprint: spec().fingerprint(),
        };
        let plan = plan_present(None, &[], &desired, None).unwrap();
        let ReconcilePlan::Create(create) = plan else {
            panic!("expected create plan");
        };
        let request = VultrLifecycleAdapter::create_request(&create, &spec());
        assert_eq!(request.method, VultrMethod::Post);
        assert_eq!(request.path, "/v2/instances");
        assert_eq!(
            request.body.unwrap()["tags"],
            json!(encode_ownership(&create.ownership()))
        );
    }

    #[test]
    fn destructive_requests_accept_only_verified_targets() {
        let target = verified_target();
        let stop = VultrLifecycleAdapter::stop_request(&target);
        let delete = VultrLifecycleAdapter::delete_request(&target);
        let snapshot = VultrLifecycleAdapter::snapshot_request(&target);
        assert_eq!(stop.path, "/v2/instances/halt");
        assert_eq!(
            delete.path,
            "/v2/instances/11111111-1111-4111-8111-111111111111"
        );
        assert_eq!(snapshot.path, "/v2/snapshots");
    }

    #[test]
    fn replacement_advances_generation_in_exact_tags() {
        let target = verified_target();
        let request = VultrLifecycleAdapter::replacement_create_request(&target, &spec()).unwrap();
        let tags = request.body.unwrap()["tags"].as_array().unwrap().clone();
        assert!(tags.contains(&json!("mobile-proxy:generation=5")));
    }

    #[test]
    fn item18_rejects_live_mutation_and_final_production_authority() {
        assert_eq!(
            VultrLifecycleAdapter::enforce_item18_live_boundary(LifecycleScope::Acceptance, true),
            Err(VultrAdapterError::Item18LiveMutationForbidden)
        );
        assert_eq!(
            VultrLifecycleAdapter::enforce_item18_live_boundary(LifecycleScope::Production, false),
            Err(VultrAdapterError::FinalProductionAuthorityForbidden)
        );
        assert!(!ITEM18_LIVE_PROVIDER_MUTATION_ALLOWED);
        assert!(!ITEM18_FINAL_PRODUCTION_AUTHORITY_ALLOWED);
    }

    #[test]
    fn adapter_preserves_domain_rejection_for_wrong_uuid() {
        let generation = Generation::new(4).unwrap();
        let metadata = OwnershipMetadata::exact(&intent(), generation);
        let observed = VultrLifecycleAdapter::decode_instance(dto(
            "22222222-2222-4222-8222-222222222222",
            encode_ownership(&metadata),
        ))
        .unwrap();
        let binding = VmBinding {
            intent: intent(),
            provider_id: ProviderResourceId::new("11111111-1111-4111-8111-111111111111").unwrap(),
            generation,
        };
        assert_eq!(
            authorize_mutation(
                &binding,
                &[observed],
                generation,
                proxy_core::MutationKind::Delete,
            ),
            Err(LifecycleError::ProviderIdentityMismatch)
        );
    }
}
