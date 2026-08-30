use crate::provider_lifecycle::{
    DesiredVm, Generation, ObservedVm, OwnershipIntent, OwnershipMetadata, OwnershipObservation,
    PlannedCreate, ProviderResourceId, VmBinding,
};
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct CreateDispatchFence {
    intent: OwnershipIntent,
    generation: Generation,
    display_name: String,
    spec_fingerprint: String,
}

impl CreateDispatchFence {
    pub fn intent(&self) -> &OwnershipIntent {
        &self.intent
    }

    pub const fn generation(&self) -> Generation {
        self.generation
    }

    pub fn display_name(&self) -> &str {
        &self.display_name
    }

    pub fn spec_fingerprint(&self) -> &str {
        &self.spec_fingerprint
    }

    pub fn ownership(&self) -> OwnershipMetadata {
        OwnershipMetadata::exact(&self.intent, self.generation)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveredCreate {
    fence: CreateDispatchFence,
    binding: VmBinding,
}

impl RecoveredCreate {
    pub fn fence(&self) -> &CreateDispatchFence {
        &self.fence
    }

    pub fn binding(&self) -> &VmBinding {
        &self.binding
    }

    pub fn provider_id(&self) -> &ProviderResourceId {
        &self.binding.provider_id
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CreateRecovery {
    AwaitProvider,
    Recovered(RecoveredCreate),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CreateDispatchError {
    OwnershipIntentMismatch,
    UnexpectedGeneration,
    DuplicateOwnershipClaim,
    ConflictingOwnershipMetadata,
    AmbiguousResourceSet,
    NeighboringOrUnboundResource,
    StaleGeneration,
    ObservedCreateMismatch,
}

impl fmt::Display for CreateDispatchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::OwnershipIntentMismatch => {
                "create plan ownership intent does not match desired VM intent"
            }
            Self::UnexpectedGeneration => "create dispatch must use generation 1",
            Self::DuplicateOwnershipClaim => {
                "multiple provider resources claim the dispatched ownership intent"
            }
            Self::ConflictingOwnershipMetadata => {
                "same-name provider resource has conflicting ownership metadata"
            }
            Self::AmbiguousResourceSet => {
                "multiple same-name provider resources make create recovery ambiguous"
            }
            Self::NeighboringOrUnboundResource => {
                "same-name neighbouring or unbound provider resource blocks create recovery"
            }
            Self::StaleGeneration => {
                "provider resource claims the dispatched intent with the wrong generation"
            }
            Self::ObservedCreateMismatch => {
                "recovered provider resource does not match dispatched name or specification"
            }
        })
    }
}

impl std::error::Error for CreateDispatchError {}

pub fn create_dispatch_fence(
    plan: &PlannedCreate,
    desired: &DesiredVm,
) -> Result<CreateDispatchFence, CreateDispatchError> {
    create_dispatch_fence_for_recovery(plan.intent(), plan.generation(), desired)
}

pub fn create_dispatch_fence_for_recovery(
    intent: &OwnershipIntent,
    generation: Generation,
    desired: &DesiredVm,
) -> Result<CreateDispatchFence, CreateDispatchError> {
    if intent != &desired.intent {
        return Err(CreateDispatchError::OwnershipIntentMismatch);
    }
    if generation != Generation::INITIAL {
        return Err(CreateDispatchError::UnexpectedGeneration);
    }
    Ok(CreateDispatchFence {
        intent: desired.intent.clone(),
        generation,
        display_name: desired.display_name.clone(),
        spec_fingerprint: desired.spec_fingerprint.clone(),
    })
}

pub fn recover_dispatched_create(
    fence: &CreateDispatchFence,
    observed: &[ObservedVm],
) -> Result<CreateRecovery, CreateDispatchError> {
    let claims: Vec<_> = observed
        .iter()
        .filter(|resource| {
            matches!(
                &resource.ownership,
                OwnershipObservation::Exact(metadata) if metadata.claims_intent(&fence.intent)
            )
        })
        .collect();
    if claims.len() > 1 {
        return Err(CreateDispatchError::DuplicateOwnershipClaim);
    }

    let same_name: Vec<_> = observed
        .iter()
        .filter(|resource| resource.display_name == fence.display_name)
        .collect();
    if same_name
        .iter()
        .any(|resource| matches!(&resource.ownership, OwnershipObservation::Conflicting))
    {
        return Err(CreateDispatchError::ConflictingOwnershipMetadata);
    }
    if same_name.len() > 1 {
        return Err(CreateDispatchError::AmbiguousResourceSet);
    }

    let Some(resource) = claims.first().copied() else {
        if same_name.len() == 1 {
            return Err(CreateDispatchError::NeighboringOrUnboundResource);
        }
        return Ok(CreateRecovery::AwaitProvider);
    };

    if same_name.len() != 1 || same_name[0].provider_id != resource.provider_id {
        return Err(CreateDispatchError::ObservedCreateMismatch);
    }
    let OwnershipObservation::Exact(metadata) = &resource.ownership else {
        unreachable!("ownership claim filter requires exact metadata");
    };
    if metadata != &fence.ownership() {
        return Err(CreateDispatchError::StaleGeneration);
    }
    if resource.spec_fingerprint != fence.spec_fingerprint {
        return Err(CreateDispatchError::ObservedCreateMismatch);
    }

    Ok(CreateRecovery::Recovered(RecoveredCreate {
        fence: fence.clone(),
        binding: VmBinding {
            intent: fence.intent.clone(),
            provider_id: resource.provider_id.clone(),
            generation: fence.generation,
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provider_lifecycle::{
        LifecycleScope, OwnershipObservation, ReconcilePlan, plan_present,
    };

    fn intent() -> OwnershipIntent {
        OwnershipIntent::new(
            LifecycleScope::Acceptance,
            "candidate:0123456789abcdef0123456789abcdef01234567",
        )
        .unwrap()
    }

    fn desired() -> DesiredVm {
        DesiredVm {
            intent: intent(),
            display_name: "mobile-proxy-acceptance".to_owned(),
            spec_fingerprint: "vultr:waw:vc2-1c-2gb:2284:mobile-proxy-acceptance".to_owned(),
        }
    }

    fn fence() -> CreateDispatchFence {
        let ReconcilePlan::Create(plan) = plan_present(None, &[], &desired(), None).unwrap() else {
            panic!("expected create plan");
        };
        create_dispatch_fence(&plan, &desired()).unwrap()
    }

    fn observed(
        id: &str,
        ownership: OwnershipObservation,
        display_name: &str,
        spec_fingerprint: &str,
    ) -> ObservedVm {
        ObservedVm {
            provider_id: ProviderResourceId::new(id).unwrap(),
            display_name: display_name.to_owned(),
            ownership,
            spec_fingerprint: spec_fingerprint.to_owned(),
        }
    }

    #[test]
    fn durable_recovery_constructor_matches_initial_dispatch_fence() {
        let desired = desired();
        let ReconcilePlan::Create(plan) = plan_present(None, &[], &desired, None).unwrap() else {
            panic!("expected create plan");
        };
        assert_eq!(
            create_dispatch_fence(&plan, &desired).unwrap(),
            create_dispatch_fence_for_recovery(plan.intent(), plan.generation(), &desired).unwrap()
        );
    }

    #[test]
    fn durable_recovery_constructor_rejects_stale_generation() {
        assert_eq!(
            create_dispatch_fence_for_recovery(&intent(), Generation::new(2).unwrap(), &desired(),),
            Err(CreateDispatchError::UnexpectedGeneration)
        );
    }

    #[test]
    fn no_resource_after_dispatch_waits_instead_of_authorizing_second_create() {
        assert_eq!(
            recover_dispatched_create(&fence(), &[]),
            Ok(CreateRecovery::AwaitProvider)
        );
    }

    #[test]
    fn one_exact_owned_resource_recovers_provider_assigned_identity() {
        let fence = fence();
        let resource = observed(
            "11111111-1111-4111-8111-111111111111",
            OwnershipObservation::Exact(fence.ownership()),
            fence.display_name(),
            fence.spec_fingerprint(),
        );
        let CreateRecovery::Recovered(recovered) =
            recover_dispatched_create(&fence, &[resource]).unwrap()
        else {
            panic!("expected recovered create");
        };
        assert_eq!(recovered.fence(), &fence);
        assert_eq!(
            recovered.provider_id().as_str(),
            "11111111-1111-4111-8111-111111111111"
        );
        assert_eq!(recovered.binding().generation, Generation::INITIAL);
    }

    #[test]
    fn duplicate_exact_ownership_claims_fail_closed() {
        let fence = fence();
        let first = observed(
            "11111111-1111-4111-8111-111111111111",
            OwnershipObservation::Exact(fence.ownership()),
            fence.display_name(),
            fence.spec_fingerprint(),
        );
        let second = observed(
            "22222222-2222-4222-8222-222222222222",
            OwnershipObservation::Exact(fence.ownership()),
            fence.display_name(),
            fence.spec_fingerprint(),
        );
        assert_eq!(
            recover_dispatched_create(&fence, &[first, second]),
            Err(CreateDispatchError::DuplicateOwnershipClaim)
        );
    }

    #[test]
    fn same_name_wrong_owner_is_not_adopted() {
        let fence = fence();
        let wrong_owner = OwnershipMetadata {
            project: "mobile-proxy".to_owned(),
            managed_by: "someone-else".to_owned(),
            scope: LifecycleScope::Acceptance,
            intent_id: fence.intent().id().to_owned(),
            generation: Generation::INITIAL,
        };
        let resource = observed(
            "11111111-1111-4111-8111-111111111111",
            OwnershipObservation::Exact(wrong_owner),
            fence.display_name(),
            fence.spec_fingerprint(),
        );
        assert_eq!(
            recover_dispatched_create(&fence, &[resource]),
            Err(CreateDispatchError::NeighboringOrUnboundResource)
        );
    }

    #[test]
    fn same_intent_wrong_generation_is_stale_not_recovered() {
        let fence = fence();
        let stale = OwnershipMetadata::exact(fence.intent(), Generation::new(2).unwrap());
        let resource = observed(
            "11111111-1111-4111-8111-111111111111",
            OwnershipObservation::Exact(stale),
            fence.display_name(),
            fence.spec_fingerprint(),
        );
        assert_eq!(
            recover_dispatched_create(&fence, &[resource]),
            Err(CreateDispatchError::StaleGeneration)
        );
    }

    #[test]
    fn exact_owner_with_wrong_spec_is_not_recovered() {
        let fence = fence();
        let resource = observed(
            "11111111-1111-4111-8111-111111111111",
            OwnershipObservation::Exact(fence.ownership()),
            fence.display_name(),
            "vultr:waw:wrong:2284:mobile-proxy-acceptance",
        );
        assert_eq!(
            recover_dispatched_create(&fence, &[resource]),
            Err(CreateDispatchError::ObservedCreateMismatch)
        );
    }
}
