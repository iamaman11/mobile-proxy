use serde::{Deserialize, Serialize};
use std::fmt;

pub const OWNERSHIP_PROJECT: &str = "mobile-proxy";
pub const OWNERSHIP_MANAGER: &str = "mobile-proxy";

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LifecycleScope {
    Acceptance,
    Production,
}

impl LifecycleScope {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Acceptance => "acceptance",
            Self::Production => "production",
        }
    }
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
pub struct OwnershipIntent {
    scope: LifecycleScope,
    id: String,
}

impl OwnershipIntent {
    pub fn new(scope: LifecycleScope, id: impl Into<String>) -> Result<Self, LifecycleValueError> {
        let id = id.into();
        if id.is_empty()
            || id.len() > 160
            || !id.bytes().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':')
            })
        {
            return Err(LifecycleValueError::InvalidOwnershipIntent);
        }
        Ok(Self { scope, id })
    }

    pub const fn scope(&self) -> LifecycleScope {
        self.scope
    }

    pub fn id(&self) -> &str {
        &self.id
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
pub struct Generation(u64);

impl Generation {
    pub const INITIAL: Self = Self(1);

    pub fn new(value: u64) -> Result<Self, LifecycleValueError> {
        if value == 0 {
            return Err(LifecycleValueError::InvalidGeneration);
        }
        Ok(Self(value))
    }

    pub const fn get(self) -> u64 {
        self.0
    }

    pub fn next(self) -> Result<Self, LifecycleValueError> {
        self.0
            .checked_add(1)
            .map(Self)
            .ok_or(LifecycleValueError::GenerationOverflow)
    }
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize, Deserialize)]
pub struct ProviderResourceId(String);

impl ProviderResourceId {
    pub fn new(value: impl Into<String>) -> Result<Self, LifecycleValueError> {
        let value = value.into();
        if value.is_empty() || value.len() > 160 || value.chars().any(char::is_whitespace) {
            return Err(LifecycleValueError::InvalidProviderResourceId);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct OwnershipMetadata {
    pub project: String,
    pub managed_by: String,
    pub scope: LifecycleScope,
    pub intent_id: String,
    pub generation: Generation,
}

impl OwnershipMetadata {
    pub fn exact(intent: &OwnershipIntent, generation: Generation) -> Self {
        Self {
            project: OWNERSHIP_PROJECT.to_owned(),
            managed_by: OWNERSHIP_MANAGER.to_owned(),
            scope: intent.scope(),
            intent_id: intent.id().to_owned(),
            generation,
        }
    }

    pub fn claims_intent(&self, intent: &OwnershipIntent) -> bool {
        self.project == OWNERSHIP_PROJECT
            && self.managed_by == OWNERSHIP_MANAGER
            && self.scope == intent.scope()
            && self.intent_id == intent.id()
    }

    fn matches_except_generation(&self, other: &Self) -> bool {
        self.project == other.project
            && self.managed_by == other.managed_by
            && self.scope == other.scope
            && self.intent_id == other.intent_id
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum OwnershipObservation {
    Exact(OwnershipMetadata),
    Missing,
    Conflicting,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObservedVm {
    pub provider_id: ProviderResourceId,
    pub display_name: String,
    pub ownership: OwnershipObservation,
    pub spec_fingerprint: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct VmBinding {
    pub intent: OwnershipIntent,
    pub provider_id: ProviderResourceId,
    pub generation: Generation,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DesiredVm {
    pub intent: OwnershipIntent,
    pub display_name: String,
    pub spec_fingerprint: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerifiedMutationTarget {
    provider_id: ProviderResourceId,
    intent: OwnershipIntent,
    generation: Generation,
}

impl VerifiedMutationTarget {
    pub fn provider_id(&self) -> &ProviderResourceId {
        &self.provider_id
    }

    pub fn intent(&self) -> &OwnershipIntent {
        &self.intent
    }

    pub const fn generation(&self) -> Generation {
        self.generation
    }

    pub fn expected_ownership(&self) -> OwnershipMetadata {
        OwnershipMetadata::exact(&self.intent, self.generation)
    }

    pub fn replacement_binding(
        &self,
        replacement_id: ProviderResourceId,
    ) -> Result<VmBinding, LifecycleValueError> {
        Ok(VmBinding {
            intent: self.intent.clone(),
            provider_id: replacement_id,
            generation: self.generation.next()?,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PlannedCreate {
    intent: OwnershipIntent,
    generation: Generation,
}

impl PlannedCreate {
    pub fn intent(&self) -> &OwnershipIntent {
        &self.intent
    }

    pub const fn generation(&self) -> Generation {
        self.generation
    }

    pub fn ownership(&self) -> OwnershipMetadata {
        OwnershipMetadata::exact(&self.intent, self.generation)
    }

    pub fn binding_after_create(&self, provider_id: ProviderResourceId) -> VmBinding {
        VmBinding {
            intent: self.intent.clone(),
            provider_id,
            generation: self.generation,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ReconcilePlan {
    Create(PlannedCreate),
    Noop(VerifiedMutationTarget),
    Reconfigure(VerifiedMutationTarget),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MutationKind {
    Stop,
    Reconfigure,
    Snapshot,
    Delete,
    Replace,
}

pub trait VmBindingStore {
    type Error;

    fn load(&self, intent: &OwnershipIntent) -> Result<Option<VmBinding>, Self::Error>;

    fn compare_and_swap(
        &mut self,
        intent: &OwnershipIntent,
        expected: Option<&VmBinding>,
        replacement: Option<VmBinding>,
    ) -> Result<(), Self::Error>;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LifecycleValueError {
    InvalidOwnershipIntent,
    InvalidGeneration,
    GenerationOverflow,
    InvalidProviderResourceId,
}

impl fmt::Display for LifecycleValueError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::InvalidOwnershipIntent => "invalid ownership intent",
            Self::InvalidGeneration => "generation must be positive",
            Self::GenerationOverflow => "generation overflow",
            Self::InvalidProviderResourceId => "invalid provider resource identity",
        })
    }
}

impl std::error::Error for LifecycleValueError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LifecycleError {
    OwnershipIntentMismatch,
    ExpectedGenerationRequired,
    UnexpectedGenerationForCreate,
    StaleGeneration,
    ProviderResourceNotFound,
    ProviderIdentityMismatch,
    MissingOwnership,
    OwnershipMetadataMismatch,
    ConflictingOwnershipMetadata,
    AmbiguousResourceSet,
    DuplicateOwnershipClaim,
    NeighboringOrUnboundResource,
}

impl fmt::Display for LifecycleError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::OwnershipIntentMismatch => {
                "binding ownership intent does not match desired intent"
            }
            Self::ExpectedGenerationRequired => {
                "expected generation is required for a bound resource"
            }
            Self::UnexpectedGenerationForCreate => {
                "expected generation is forbidden when no binding exists"
            }
            Self::StaleGeneration => "expected or provider ownership generation is stale",
            Self::ProviderResourceNotFound => "bound provider resource was not found",
            Self::ProviderIdentityMismatch => {
                "provider resource identity does not match the binding"
            }
            Self::MissingOwnership => "bound provider resource is missing ownership metadata",
            Self::OwnershipMetadataMismatch => {
                "provider ownership metadata does not exactly match the binding"
            }
            Self::ConflictingOwnershipMetadata => {
                "provider ownership metadata is conflicting or ambiguous"
            }
            Self::AmbiguousResourceSet => "multiple neighbouring resources are ambiguous",
            Self::DuplicateOwnershipClaim => {
                "multiple provider resources claim the same ownership intent"
            }
            Self::NeighboringOrUnboundResource => {
                "neighbouring or unbound provider resource cannot be managed"
            }
        })
    }
}

impl std::error::Error for LifecycleError {}

pub fn plan_present(
    binding: Option<&VmBinding>,
    observed: &[ObservedVm],
    desired: &DesiredVm,
    expected_generation: Option<Generation>,
) -> Result<ReconcilePlan, LifecycleError> {
    match binding {
        None => plan_unbound(observed, desired, expected_generation),
        Some(binding) => plan_bound(binding, observed, desired, expected_generation),
    }
}

pub fn authorize_mutation(
    binding: &VmBinding,
    observed: &[ObservedVm],
    expected_generation: Generation,
    _kind: MutationKind,
) -> Result<VerifiedMutationTarget, LifecycleError> {
    resolve_bound_resource(binding, observed, expected_generation)
}

fn plan_unbound(
    observed: &[ObservedVm],
    desired: &DesiredVm,
    expected_generation: Option<Generation>,
) -> Result<ReconcilePlan, LifecycleError> {
    if expected_generation.is_some() {
        return Err(LifecycleError::UnexpectedGenerationForCreate);
    }

    let claims = ownership_claims(observed, &desired.intent);
    if claims.len() > 1 {
        return Err(LifecycleError::DuplicateOwnershipClaim);
    }
    if claims.len() == 1 {
        return Err(LifecycleError::NeighboringOrUnboundResource);
    }

    let same_name: Vec<_> = observed
        .iter()
        .filter(|resource| resource.display_name == desired.display_name)
        .collect();
    if same_name
        .iter()
        .any(|resource| matches!(&resource.ownership, OwnershipObservation::Conflicting))
    {
        return Err(LifecycleError::ConflictingOwnershipMetadata);
    }
    if same_name.len() > 1 {
        return Err(LifecycleError::AmbiguousResourceSet);
    }
    if same_name.len() == 1 {
        return Err(LifecycleError::NeighboringOrUnboundResource);
    }

    Ok(ReconcilePlan::Create(PlannedCreate {
        intent: desired.intent.clone(),
        generation: Generation::INITIAL,
    }))
}

fn plan_bound(
    binding: &VmBinding,
    observed: &[ObservedVm],
    desired: &DesiredVm,
    expected_generation: Option<Generation>,
) -> Result<ReconcilePlan, LifecycleError> {
    if binding.intent != desired.intent {
        return Err(LifecycleError::OwnershipIntentMismatch);
    }
    let expected_generation =
        expected_generation.ok_or(LifecycleError::ExpectedGenerationRequired)?;
    let target = resolve_bound_resource(binding, observed, expected_generation)?;
    let resource = observed
        .iter()
        .find(|resource| resource.provider_id == *target.provider_id())
        .ok_or(LifecycleError::ProviderResourceNotFound)?;

    if resource.spec_fingerprint == desired.spec_fingerprint {
        Ok(ReconcilePlan::Noop(target))
    } else {
        Ok(ReconcilePlan::Reconfigure(target))
    }
}

fn resolve_bound_resource(
    binding: &VmBinding,
    observed: &[ObservedVm],
    expected_generation: Generation,
) -> Result<VerifiedMutationTarget, LifecycleError> {
    if binding.generation != expected_generation {
        return Err(LifecycleError::StaleGeneration);
    }

    let expected_metadata = OwnershipMetadata::exact(&binding.intent, binding.generation);
    if let Some(bound_observation) = observed
        .iter()
        .find(|resource| resource.provider_id == binding.provider_id)
    {
        match &bound_observation.ownership {
            OwnershipObservation::Missing => return Err(LifecycleError::MissingOwnership),
            OwnershipObservation::Conflicting => {
                return Err(LifecycleError::ConflictingOwnershipMetadata);
            }
            OwnershipObservation::Exact(metadata) if metadata != &expected_metadata => {
                if metadata.matches_except_generation(&expected_metadata) {
                    return Err(LifecycleError::StaleGeneration);
                }
                return Err(LifecycleError::OwnershipMetadataMismatch);
            }
            OwnershipObservation::Exact(_) => {}
        }
    }

    let claims = ownership_claims(observed, &binding.intent);
    if claims.len() > 1 {
        return Err(LifecycleError::DuplicateOwnershipClaim);
    }
    let resource = claims
        .first()
        .copied()
        .ok_or(LifecycleError::ProviderResourceNotFound)?;

    if resource.provider_id != binding.provider_id {
        return Err(LifecycleError::ProviderIdentityMismatch);
    }

    let OwnershipObservation::Exact(metadata) = &resource.ownership else {
        return Err(LifecycleError::MissingOwnership);
    };
    if metadata != &expected_metadata {
        if metadata.matches_except_generation(&expected_metadata) {
            return Err(LifecycleError::StaleGeneration);
        }
        return Err(LifecycleError::OwnershipMetadataMismatch);
    }

    Ok(VerifiedMutationTarget {
        provider_id: binding.provider_id.clone(),
        intent: binding.intent.clone(),
        generation: binding.generation,
    })
}

fn ownership_claims<'a>(
    observed: &'a [ObservedVm],
    intent: &OwnershipIntent,
) -> Vec<&'a ObservedVm> {
    observed
        .iter()
        .filter(|resource| {
            matches!(
                &resource.ownership,
                OwnershipObservation::Exact(metadata) if metadata.claims_intent(intent)
            )
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn intent() -> OwnershipIntent {
        OwnershipIntent::new(LifecycleScope::Acceptance, "candidate:0123456789abcdef").unwrap()
    }

    fn provider_id(value: &str) -> ProviderResourceId {
        ProviderResourceId::new(value).unwrap()
    }

    fn binding() -> VmBinding {
        VmBinding {
            intent: intent(),
            provider_id: provider_id("11111111-1111-4111-8111-111111111111"),
            generation: Generation::new(7).unwrap(),
        }
    }

    fn desired() -> DesiredVm {
        DesiredVm {
            intent: intent(),
            display_name: "mobile-proxy-acceptance".to_owned(),
            spec_fingerprint: "spec:v1".to_owned(),
        }
    }

    fn owned(id: &str, generation: Generation, fingerprint: &str) -> ObservedVm {
        ObservedVm {
            provider_id: provider_id(id),
            display_name: "mobile-proxy-acceptance".to_owned(),
            ownership: OwnershipObservation::Exact(OwnershipMetadata::exact(&intent(), generation)),
            spec_fingerprint: fingerprint.to_owned(),
        }
    }

    #[test]
    fn clean_unbound_state_plans_one_create() {
        let plan = plan_present(None, &[], &desired(), None).unwrap();
        let ReconcilePlan::Create(create) = plan else {
            panic!("expected create plan");
        };
        assert_eq!(create.generation(), Generation::INITIAL);
        assert_eq!(
            create.ownership(),
            OwnershipMetadata::exact(&intent(), Generation::INITIAL)
        );
    }

    #[test]
    fn repeated_reconcile_is_idempotent_when_spec_matches() {
        let binding = binding();
        let observed = vec![owned(
            binding.provider_id.as_str(),
            binding.generation,
            "spec:v1",
        )];
        assert!(matches!(
            plan_present(
                Some(&binding),
                &observed,
                &desired(),
                Some(binding.generation)
            ),
            Ok(ReconcilePlan::Noop(_))
        ));
    }

    #[test]
    fn changed_spec_requires_verified_reconfigure() {
        let binding = binding();
        let observed = vec![owned(
            binding.provider_id.as_str(),
            binding.generation,
            "spec:old",
        )];
        assert!(matches!(
            plan_present(
                Some(&binding),
                &observed,
                &desired(),
                Some(binding.generation)
            ),
            Ok(ReconcilePlan::Reconfigure(_))
        ));
    }

    #[test]
    fn ambiguous_neighbouring_resources_are_rejected() {
        let neighbour_a = ObservedVm {
            provider_id: provider_id("22222222-2222-4222-8222-222222222222"),
            display_name: desired().display_name,
            ownership: OwnershipObservation::Missing,
            spec_fingerprint: "spec:v1".to_owned(),
        };
        let mut neighbour_b = neighbour_a.clone();
        neighbour_b.provider_id = provider_id("33333333-3333-4333-8333-333333333333");
        assert_eq!(
            plan_present(None, &[neighbour_a, neighbour_b], &desired(), None),
            Err(LifecycleError::AmbiguousResourceSet)
        );
    }

    #[test]
    fn same_name_wrong_owner_is_rejected() {
        let neighbour = ObservedVm {
            provider_id: provider_id("22222222-2222-4222-8222-222222222222"),
            display_name: desired().display_name,
            ownership: OwnershipObservation::Missing,
            spec_fingerprint: "spec:v1".to_owned(),
        };
        assert_eq!(
            plan_present(None, &[neighbour], &desired(), None),
            Err(LifecycleError::NeighboringOrUnboundResource)
        );
    }

    #[test]
    fn correct_ownership_with_wrong_uuid_is_rejected() {
        let binding = binding();
        let observed = vec![owned(
            "22222222-2222-4222-8222-222222222222",
            binding.generation,
            "spec:v1",
        )];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Delete,
            ),
            Err(LifecycleError::ProviderIdentityMismatch)
        );
    }

    #[test]
    fn stale_expected_generation_is_rejected() {
        let binding = binding();
        let observed = vec![owned(
            binding.provider_id.as_str(),
            binding.generation,
            "spec:v1",
        )];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                Generation::new(6).unwrap(),
                MutationKind::Stop,
            ),
            Err(LifecycleError::StaleGeneration)
        );
    }

    #[test]
    fn stale_provider_generation_is_rejected() {
        let binding = binding();
        let observed = vec![owned(
            binding.provider_id.as_str(),
            Generation::new(6).unwrap(),
            "spec:v1",
        )];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Reconfigure,
            ),
            Err(LifecycleError::StaleGeneration)
        );
    }

    #[test]
    fn bound_uuid_with_wrong_exact_owner_is_not_treated_as_deleted() {
        let binding = binding();
        let wrong_intent =
            OwnershipIntent::new(LifecycleScope::Acceptance, "candidate:different").unwrap();
        let observed = vec![ObservedVm {
            provider_id: binding.provider_id.clone(),
            display_name: desired().display_name,
            ownership: OwnershipObservation::Exact(OwnershipMetadata::exact(
                &wrong_intent,
                binding.generation,
            )),
            spec_fingerprint: "spec:v1".to_owned(),
        }];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Delete,
            ),
            Err(LifecycleError::OwnershipMetadataMismatch)
        );
    }

    #[test]
    fn truly_absent_bound_uuid_is_reported_not_found() {
        let binding = binding();
        assert_eq!(
            authorize_mutation(&binding, &[], binding.generation, MutationKind::Delete,),
            Err(LifecycleError::ProviderResourceNotFound)
        );
    }

    #[test]
    fn missing_ownership_on_bound_uuid_is_rejected() {
        let binding = binding();
        let observed = vec![ObservedVm {
            provider_id: binding.provider_id.clone(),
            display_name: desired().display_name,
            ownership: OwnershipObservation::Missing,
            spec_fingerprint: "spec:v1".to_owned(),
        }];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Snapshot,
            ),
            Err(LifecycleError::MissingOwnership)
        );
    }

    #[test]
    fn duplicate_ownership_claims_are_rejected() {
        let binding = binding();
        let observed = vec![
            owned(binding.provider_id.as_str(), binding.generation, "spec:v1"),
            owned(
                "22222222-2222-4222-8222-222222222222",
                binding.generation,
                "spec:v1",
            ),
        ];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Replace,
            ),
            Err(LifecycleError::DuplicateOwnershipClaim)
        );
    }

    #[test]
    fn conflicting_ownership_on_bound_uuid_is_rejected() {
        let binding = binding();
        let observed = vec![ObservedVm {
            provider_id: binding.provider_id.clone(),
            display_name: desired().display_name,
            ownership: OwnershipObservation::Conflicting,
            spec_fingerprint: "spec:v1".to_owned(),
        }];
        assert_eq!(
            authorize_mutation(
                &binding,
                &observed,
                binding.generation,
                MutationKind::Delete,
            ),
            Err(LifecycleError::ConflictingOwnershipMetadata)
        );
    }

    #[derive(Default)]
    struct MemoryStore {
        bindings: BTreeMap<OwnershipIntent, VmBinding>,
    }

    #[derive(Debug, Eq, PartialEq)]
    enum StoreError {
        CompareAndSwapConflict,
    }

    impl VmBindingStore for MemoryStore {
        type Error = StoreError;

        fn load(&self, intent: &OwnershipIntent) -> Result<Option<VmBinding>, Self::Error> {
            Ok(self.bindings.get(intent).cloned())
        }

        fn compare_and_swap(
            &mut self,
            intent: &OwnershipIntent,
            expected: Option<&VmBinding>,
            replacement: Option<VmBinding>,
        ) -> Result<(), Self::Error> {
            if self.bindings.get(intent) != expected {
                return Err(StoreError::CompareAndSwapConflict);
            }
            match replacement {
                Some(binding) => {
                    self.bindings.insert(intent.clone(), binding);
                }
                None => {
                    self.bindings.remove(intent);
                }
            }
            Ok(())
        }
    }

    #[test]
    fn binding_store_compare_and_swap_rejects_stale_actor() {
        let current = binding();
        let mut store = MemoryStore::default();
        store
            .compare_and_swap(&current.intent, None, Some(current.clone()))
            .unwrap();
        let stale = VmBinding {
            generation: Generation::new(6).unwrap(),
            ..current.clone()
        };
        assert_eq!(
            store.compare_and_swap(&current.intent, Some(&stale), None),
            Err(StoreError::CompareAndSwapConflict)
        );
        assert_eq!(store.load(&current.intent).unwrap(), Some(current));
    }
}
