use anyhow::{Result, bail};
use proxy_core::provider_create_dispatch::{
    CreateRecovery, create_dispatch_fence, create_dispatch_fence_for_recovery,
    recover_dispatched_create,
};
use proxy_core::{
    Generation, LifecycleError, MutationKind, ObservedVm, OwnershipIntent, PlannedCreate,
    ReconcilePlan, VerifiedMutationTarget, VmBinding, VmBindingStore, authorize_mutation,
    plan_present,
};
use std::net::Ipv4Addr;
use std::thread;
use std::time::Duration;

use crate::github_vm_binding_store::{AcceptanceVmLifecycleState, DurableGitHubVmBindingStore};
use crate::item20_acceptance::{Item20SessionIdentity, acceptance_spec};
use crate::vultr_client::VultrAcceptanceClient;
use crate::vultr_lifecycle::VultrVmSpec;

const CREATE_RECOVERY_ATTEMPTS: usize = 20;
const CREATE_RECOVERY_DELAY: Duration = Duration::from_secs(3);
const DELETE_CONFIRM_ATTEMPTS: usize = 40;
const DELETE_CONFIRM_DELAY: Duration = Duration::from_secs(3);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionOpenOrigin {
    Existing,
    Created,
    Recovered,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OpenItem20Session {
    pub binding: VmBinding,
    pub origin: SessionOpenOrigin,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionCloseOutcome {
    NoResourceCreated,
    DeletedAndTerminal,
    AlreadyTerminal,
}

pub trait Item20LifecycleStore: VmBindingStore {
    fn lifecycle_state(
        &self,
        intent: &OwnershipIntent,
    ) -> std::result::Result<AcceptanceVmLifecycleState, Self::Error>;

    fn prepare_create(
        &mut self,
        intent: &OwnershipIntent,
    ) -> std::result::Result<Generation, Self::Error>;

    fn mark_create_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        generation: Generation,
    ) -> std::result::Result<(), Self::Error>;

    fn prepare_delete(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> std::result::Result<(), Self::Error>;

    fn mark_delete_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> std::result::Result<(), Self::Error>;
}

impl Item20LifecycleStore for DurableGitHubVmBindingStore {
    fn lifecycle_state(
        &self,
        intent: &OwnershipIntent,
    ) -> std::result::Result<AcceptanceVmLifecycleState, Self::Error> {
        DurableGitHubVmBindingStore::lifecycle_state(self, intent)
    }

    fn prepare_create(
        &mut self,
        intent: &OwnershipIntent,
    ) -> std::result::Result<Generation, Self::Error> {
        DurableGitHubVmBindingStore::prepare_create(self, intent)
    }

    fn mark_create_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        generation: Generation,
    ) -> std::result::Result<(), Self::Error> {
        DurableGitHubVmBindingStore::mark_create_dispatched(self, intent, generation)
    }

    fn prepare_delete(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> std::result::Result<(), Self::Error> {
        DurableGitHubVmBindingStore::prepare_delete(self, intent, binding)
    }

    fn mark_delete_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> std::result::Result<(), Self::Error> {
        DurableGitHubVmBindingStore::mark_delete_dispatched(self, intent, binding)
    }
}

pub trait Item20AcceptanceProvider {
    type Error;

    fn list_instances(&self) -> std::result::Result<Vec<ObservedVm>, Self::Error>;

    fn create_instance_with_user_data(
        &self,
        plan: &PlannedCreate,
        spec: &VultrVmSpec,
        user_data_b64: &str,
    ) -> std::result::Result<ObservedVm, Self::Error>;

    fn instance_ipv4(
        &self,
        target: &VerifiedMutationTarget,
    ) -> std::result::Result<Ipv4Addr, Self::Error>;

    fn delete_instance(
        &self,
        target: &VerifiedMutationTarget,
    ) -> std::result::Result<(), Self::Error>;
}

impl Item20AcceptanceProvider for VultrAcceptanceClient {
    type Error = crate::vultr_client::VultrClientError;

    fn list_instances(&self) -> std::result::Result<Vec<ObservedVm>, Self::Error> {
        VultrAcceptanceClient::list_instances(self)
    }

    fn create_instance_with_user_data(
        &self,
        plan: &PlannedCreate,
        spec: &VultrVmSpec,
        user_data_b64: &str,
    ) -> std::result::Result<ObservedVm, Self::Error> {
        VultrAcceptanceClient::create_instance_with_user_data(self, plan, spec, user_data_b64)
    }

    fn instance_ipv4(
        &self,
        target: &VerifiedMutationTarget,
    ) -> std::result::Result<Ipv4Addr, Self::Error> {
        VultrAcceptanceClient::instance_ipv4(self, target)
    }

    fn delete_instance(
        &self,
        target: &VerifiedMutationTarget,
    ) -> std::result::Result<(), Self::Error> {
        VultrAcceptanceClient::delete_instance(self, target)
    }
}

pub fn open_item20_session<S, P>(
    store: &mut S,
    provider: &P,
    identity: &Item20SessionIdentity,
    user_data_b64: &str,
) -> Result<OpenItem20Session>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let desired = identity.desired_vm()?;
    let (binding, origin) = match store.lifecycle_state(&desired.intent)? {
        AcceptanceVmLifecycleState::Empty => (
            dispatch_create(store, provider, &desired, user_data_b64, None)?,
            SessionOpenOrigin::Created,
        ),
        AcceptanceVmLifecycleState::CreatePrepared { generation } => (
            dispatch_create(store, provider, &desired, user_data_b64, Some(generation))?,
            SessionOpenOrigin::Created,
        ),
        AcceptanceVmLifecycleState::CreateDispatched { generation } => (
            recover_create_binding(store, provider, &desired, generation)?,
            SessionOpenOrigin::Recovered,
        ),
        AcceptanceVmLifecycleState::Bound(binding) => {
            let observed = provider.list_instances()?;
            match plan_present(
                Some(&binding),
                &observed,
                &desired,
                Some(binding.generation),
            )? {
                ReconcilePlan::Noop(_) => (binding, SessionOpenOrigin::Existing),
                ReconcilePlan::Reconfigure(_) => {
                    bail!("bound Item 20 acceptance VM specification drifted")
                }
                ReconcilePlan::Create(_) => {
                    bail!("bound Item 20 acceptance state unexpectedly planned another create")
                }
            }
        }
        AcceptanceVmLifecycleState::DeletePrepared(_)
        | AcceptanceVmLifecycleState::DeleteDispatched(_) => {
            bail!("Item 20 acceptance-session cleanup is already in progress")
        }
        AcceptanceVmLifecycleState::Terminal { .. } => {
            bail!("terminal Item 20 acceptance intent cannot be reused")
        }
    };

    Ok(OpenItem20Session { binding, origin })
}

pub fn verified_item20_target<P>(
    provider: &P,
    identity: &Item20SessionIdentity,
    binding: &VmBinding,
) -> Result<VerifiedMutationTarget>
where
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let desired = identity.desired_vm()?;
    if binding.intent != desired.intent {
        bail!("Item 20 binding does not match the admitted session identity");
    }
    let observed = provider.list_instances()?;
    match plan_present(Some(binding), &observed, &desired, Some(binding.generation))? {
        ReconcilePlan::Noop(target) => Ok(target),
        ReconcilePlan::Reconfigure(_) => {
            bail!("Item 20 acceptance VM specification drifted before target resolution")
        }
        ReconcilePlan::Create(_) => {
            bail!("bound Item 20 acceptance VM unexpectedly resolved as create")
        }
    }
}

pub fn verified_item20_endpoint<P>(
    provider: &P,
    identity: &Item20SessionIdentity,
    binding: &VmBinding,
) -> Result<Ipv4Addr>
where
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let target = verified_item20_target(provider, identity, binding)?;
    Ok(provider.instance_ipv4(&target)?)
}

pub fn close_item20_session<S, P>(
    store: &mut S,
    provider: &P,
    identity: &Item20SessionIdentity,
) -> Result<SessionCloseOutcome>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let desired = identity.desired_vm()?;
    match store.lifecycle_state(&desired.intent)? {
        AcceptanceVmLifecycleState::Empty => Ok(SessionCloseOutcome::NoResourceCreated),
        AcceptanceVmLifecycleState::CreatePrepared { .. } => {
            bail!("Item 20 create was prepared but never dispatch-fenced; retry open before close")
        }
        AcceptanceVmLifecycleState::CreateDispatched { generation } => {
            let binding = recover_create_binding(store, provider, &desired, generation)?;
            delete_bound(store, provider, &binding, false, false)?;
            Ok(SessionCloseOutcome::DeletedAndTerminal)
        }
        AcceptanceVmLifecycleState::Bound(binding) => {
            delete_bound(store, provider, &binding, false, false)?;
            Ok(SessionCloseOutcome::DeletedAndTerminal)
        }
        AcceptanceVmLifecycleState::DeletePrepared(binding) => {
            delete_bound(store, provider, &binding, true, false)?;
            Ok(SessionCloseOutcome::DeletedAndTerminal)
        }
        AcceptanceVmLifecycleState::DeleteDispatched(binding) => {
            recover_dispatched_delete(store, provider, &binding)?;
            Ok(SessionCloseOutcome::DeletedAndTerminal)
        }
        AcceptanceVmLifecycleState::Terminal { .. } => Ok(SessionCloseOutcome::AlreadyTerminal),
    }
}

fn dispatch_create<S, P>(
    store: &mut S,
    provider: &P,
    desired: &proxy_core::DesiredVm,
    user_data_b64: &str,
    prepared_generation: Option<Generation>,
) -> Result<VmBinding>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let observed = provider.list_instances()?;
    let ReconcilePlan::Create(plan) = plan_present(None, &observed, desired, None)? else {
        bail!("unbound Item 20 intent is not eligible for exactly one create");
    };
    let fence = create_dispatch_fence(&plan, desired)?;
    let generation = match prepared_generation {
        Some(generation) => generation,
        None => store.prepare_create(&desired.intent)?,
    };
    if generation != fence.generation() {
        bail!("durable Item 20 create generation does not match provider-neutral create plan");
    }
    store.mark_create_dispatched(&desired.intent, generation)?;

    if provider
        .create_instance_with_user_data(&plan, &acceptance_spec(), user_data_b64)
        .is_err()
    {
        bail!(
            "Item 20 acceptance VM create dispatch outcome is ambiguous; retry the exact admitted session for durable recovery"
        );
    }
    recover_create_binding(store, provider, desired, generation)
}

fn recover_create_binding<S, P>(
    store: &mut S,
    provider: &P,
    desired: &proxy_core::DesiredVm,
    generation: Generation,
) -> Result<VmBinding>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let fence = create_dispatch_fence_for_recovery(&desired.intent, generation, desired)?;
    for attempt in 0..CREATE_RECOVERY_ATTEMPTS {
        let observed = provider.list_instances()?;
        match recover_dispatched_create(&fence, &observed)? {
            CreateRecovery::AwaitProvider => {
                if attempt + 1 < CREATE_RECOVERY_ATTEMPTS {
                    thread::sleep(CREATE_RECOVERY_DELAY);
                }
            }
            CreateRecovery::Recovered(recovered) => {
                let binding = recovered.binding().clone();
                store.compare_and_swap(&desired.intent, None, Some(binding.clone()))?;
                return Ok(binding);
            }
        }
    }
    bail!("dispatched Item 20 acceptance VM create did not converge within bounded recovery window")
}

fn delete_bound<S, P>(
    store: &mut S,
    provider: &P,
    binding: &VmBinding,
    already_prepared: bool,
    already_dispatched: bool,
) -> Result<()>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let target = resolve_delete_target(provider, binding)?;
    if !already_prepared {
        store.prepare_delete(&binding.intent, binding)?;
    }
    if !already_dispatched {
        store.mark_delete_dispatched(&binding.intent, binding)?;
    }
    provider.delete_instance(&target)?;
    confirm_provider_deleted(provider, binding)?;
    store.compare_and_swap(&binding.intent, Some(binding), None)?;
    if !terminal_matches(store, binding)? {
        bail!("Item 20 durable lifecycle did not reach terminal after confirmed provider delete");
    }
    Ok(())
}

fn resolve_delete_target<P>(provider: &P, binding: &VmBinding) -> Result<VerifiedMutationTarget>
where
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let observed = provider.list_instances()?;
    Ok(authorize_mutation(
        binding,
        &observed,
        binding.generation,
        MutationKind::Delete,
    )?)
}

fn confirm_provider_deleted<P>(provider: &P, binding: &VmBinding) -> Result<()>
where
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    for attempt in 0..DELETE_CONFIRM_ATTEMPTS {
        let observed = provider.list_instances()?;
        match authorize_mutation(binding, &observed, binding.generation, MutationKind::Delete) {
            Err(LifecycleError::ProviderResourceNotFound) => return Ok(()),
            Ok(_) => {
                if attempt + 1 < DELETE_CONFIRM_ATTEMPTS {
                    thread::sleep(DELETE_CONFIRM_DELAY);
                }
            }
            Err(error) => return Err(error.into()),
        }
    }
    bail!("exact Item 20 acceptance VM deletion was not confirmed within bounded window")
}

fn recover_dispatched_delete<S, P>(store: &mut S, provider: &P, binding: &VmBinding) -> Result<()>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
    P: Item20AcceptanceProvider,
    P::Error: std::error::Error + Send + Sync + 'static,
{
    let observed = provider.list_instances()?;
    match authorize_mutation(binding, &observed, binding.generation, MutationKind::Delete) {
        Err(LifecycleError::ProviderResourceNotFound) => {
            store.compare_and_swap(&binding.intent, Some(binding), None)?;
        }
        Ok(target) => {
            provider.delete_instance(&target)?;
            confirm_provider_deleted(provider, binding)?;
            store.compare_and_swap(&binding.intent, Some(binding), None)?;
        }
        Err(error) => return Err(error.into()),
    }
    if !terminal_matches(store, binding)? {
        bail!("Item 20 durable lifecycle did not reach terminal during delete recovery");
    }
    Ok(())
}

fn terminal_matches<S>(store: &S, binding: &VmBinding) -> Result<bool>
where
    S: Item20LifecycleStore,
    S::Error: std::error::Error + Send + Sync + 'static,
{
    Ok(matches!(
        store.lifecycle_state(&binding.intent)?,
        AcceptanceVmLifecycleState::Terminal { last_generation }
            if last_generation == binding.generation
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use proxy_core::{DesiredVm, OwnershipMetadata, OwnershipObservation, ProviderResourceId};
    use std::cell::{Cell, RefCell};
    use std::io;

    const CANDIDATE: &str = "d151dbdd156279e32a5361d304c90f996bd2d565";
    const CONTROL_PLANE: &str = "a4f014cb4f567b9c525ebd2ea30c66b2d12c18db";
    const PROVIDER_ID: &str = "11111111-1111-4111-8111-111111111111";

    fn identity() -> Item20SessionIdentity {
        Item20SessionIdentity::new(CANDIDATE, CONTROL_PLANE).unwrap()
    }

    #[derive(Clone)]
    struct MemoryStore {
        intent: OwnershipIntent,
        state: AcceptanceVmLifecycleState,
    }

    impl MemoryStore {
        fn new(identity: &Item20SessionIdentity) -> Self {
            Self {
                intent: identity.ownership_intent().unwrap(),
                state: AcceptanceVmLifecycleState::Empty,
            }
        }

        fn invalid_transition() -> io::Error {
            io::Error::other("invalid test transition")
        }
    }

    impl VmBindingStore for MemoryStore {
        type Error = io::Error;

        fn load(&self, intent: &OwnershipIntent) -> io::Result<Option<VmBinding>> {
            if intent != &self.intent {
                return Err(Self::invalid_transition());
            }
            match &self.state {
                AcceptanceVmLifecycleState::Bound(binding) => Ok(Some(binding.clone())),
                AcceptanceVmLifecycleState::Empty => Ok(None),
                _ => Err(Self::invalid_transition()),
            }
        }

        fn compare_and_swap(
            &mut self,
            intent: &OwnershipIntent,
            expected: Option<&VmBinding>,
            replacement: Option<VmBinding>,
        ) -> io::Result<()> {
            if intent != &self.intent {
                return Err(Self::invalid_transition());
            }
            match (&self.state, expected, replacement) {
                (
                    AcceptanceVmLifecycleState::CreateDispatched { generation },
                    None,
                    Some(binding),
                ) if *generation == binding.generation && binding.intent == self.intent => {
                    self.state = AcceptanceVmLifecycleState::Bound(binding);
                    Ok(())
                }
                (AcceptanceVmLifecycleState::DeleteDispatched(current), Some(expected), None)
                    if current == expected =>
                {
                    self.state = AcceptanceVmLifecycleState::Terminal {
                        last_generation: current.generation,
                    };
                    Ok(())
                }
                _ => Err(Self::invalid_transition()),
            }
        }
    }

    impl Item20LifecycleStore for MemoryStore {
        fn lifecycle_state(
            &self,
            intent: &OwnershipIntent,
        ) -> io::Result<AcceptanceVmLifecycleState> {
            if intent != &self.intent {
                return Err(Self::invalid_transition());
            }
            Ok(self.state.clone())
        }

        fn prepare_create(&mut self, intent: &OwnershipIntent) -> io::Result<Generation> {
            if intent != &self.intent || !matches!(self.state, AcceptanceVmLifecycleState::Empty) {
                return Err(Self::invalid_transition());
            }
            let generation = Generation::INITIAL;
            self.state = AcceptanceVmLifecycleState::CreatePrepared { generation };
            Ok(generation)
        }

        fn mark_create_dispatched(
            &mut self,
            intent: &OwnershipIntent,
            generation: Generation,
        ) -> io::Result<()> {
            if intent != &self.intent || self.state != AcceptanceVmLifecycleState::CreatePrepared {
                generation
            }
            {
                return Err(Self::invalid_transition());
            }
            self.state = AcceptanceVmLifecycleState::CreateDispatched { generation };
            Ok(())
        }

        fn prepare_delete(
            &mut self,
            intent: &OwnershipIntent,
            binding: &VmBinding,
        ) -> io::Result<()> {
            if intent != &self.intent
                || self.state != AcceptanceVmLifecycleState::Bound(binding.clone())
            {
                return Err(Self::invalid_transition());
            }
            self.state = AcceptanceVmLifecycleState::DeletePrepared(binding.clone());
            Ok(())
        }

        fn mark_delete_dispatched(
            &mut self,
            intent: &OwnershipIntent,
            binding: &VmBinding,
        ) -> io::Result<()> {
            if intent != &self.intent
                || self.state != AcceptanceVmLifecycleState::DeletePrepared(binding.clone())
            {
                return Err(Self::invalid_transition());
            }
            self.state = AcceptanceVmLifecycleState::DeleteDispatched(binding.clone());
            Ok(())
        }
    }

    #[derive(Default)]
    struct FakeProvider {
        observed: RefCell<Vec<ObservedVm>>,
        create_calls: Cell<usize>,
        delete_calls: Cell<usize>,
    }

    impl FakeProvider {
        fn exact_observed(identity: &Item20SessionIdentity, id: &str) -> ObservedVm {
            let desired = identity.desired_vm().unwrap();
            ObservedVm {
                provider_id: ProviderResourceId::new(id).unwrap(),
                display_name: desired.display_name,
                ownership: OwnershipObservation::Exact(OwnershipMetadata::exact(
                    &desired.intent,
                    Generation::INITIAL,
                )),
                spec_fingerprint: desired.spec_fingerprint,
            }
        }
    }

    impl Item20AcceptanceProvider for FakeProvider {
        type Error = io::Error;

        fn list_instances(&self) -> io::Result<Vec<ObservedVm>> {
            Ok(self.observed.borrow().clone())
        }

        fn create_instance_with_user_data(
            &self,
            plan: &PlannedCreate,
            spec: &VultrVmSpec,
            _user_data_b64: &str,
        ) -> io::Result<ObservedVm> {
            self.create_calls.set(self.create_calls.get() + 1);
            let resource = ObservedVm {
                provider_id: ProviderResourceId::new(PROVIDER_ID).unwrap(),
                display_name: spec.label.clone(),
                ownership: OwnershipObservation::Exact(plan.ownership()),
                spec_fingerprint: spec.fingerprint(),
            };
            self.observed.borrow_mut().push(resource.clone());
            Ok(resource)
        }

        fn instance_ipv4(&self, _target: &VerifiedMutationTarget) -> io::Result<Ipv4Addr> {
            Ok(Ipv4Addr::new(1, 1, 1, 1))
        }

        fn delete_instance(&self, target: &VerifiedMutationTarget) -> io::Result<()> {
            self.delete_calls.set(self.delete_calls.get() + 1);
            self.observed
                .borrow_mut()
                .retain(|resource| resource.provider_id != *target.provider_id());
            Ok(())
        }
    }

    fn open_once(store: &mut MemoryStore, provider: &FakeProvider) -> OpenItem20Session {
        open_item20_session(store, provider, &identity(), "test-cloud-init").unwrap()
    }

    #[test]
    fn empty_session_creates_exactly_once_and_binds() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let provider = FakeProvider::default();
        let opened = open_once(&mut store, &provider);
        assert_eq!(opened.origin, SessionOpenOrigin::Created);
        assert_eq!(provider.create_calls.get(), 1);
        assert_eq!(opened.binding.intent, identity.ownership_intent().unwrap());
        assert!(matches!(
            store.state,
            AcceptanceVmLifecycleState::Bound(ref binding) if binding == &opened.binding
        ));
    }

    #[test]
    fn bound_retry_is_noop_and_never_creates_again() {
        let mut store = MemoryStore::new(&identity());
        let provider = FakeProvider::default();
        let first = open_once(&mut store, &provider);
        let second = open_once(&mut store, &provider);
        assert_eq!(first.binding, second.binding);
        assert_eq!(second.origin, SessionOpenOrigin::Existing);
        assert_eq!(provider.create_calls.get(), 1);
    }

    #[test]
    fn dispatched_create_recovers_provider_identity_without_second_post() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let intent = identity.ownership_intent().unwrap();
        let generation = store.prepare_create(&intent).unwrap();
        store.mark_create_dispatched(&intent, generation).unwrap();
        let provider = FakeProvider::default();
        provider
            .observed
            .borrow_mut()
            .push(FakeProvider::exact_observed(&identity, PROVIDER_ID));

        let opened = open_once(&mut store, &provider);
        assert_eq!(opened.origin, SessionOpenOrigin::Recovered);
        assert_eq!(provider.create_calls.get(), 0);
        assert_eq!(opened.binding.provider_id.as_str(), PROVIDER_ID);
    }

    #[test]
    fn neighbouring_same_name_resource_blocks_create_without_mutation() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let provider = FakeProvider::default();
        let desired: DesiredVm = identity.desired_vm().unwrap();
        provider.observed.borrow_mut().push(ObservedVm {
            provider_id: ProviderResourceId::new("22222222-2222-4222-8222-222222222222").unwrap(),
            display_name: desired.display_name,
            ownership: OwnershipObservation::Missing,
            spec_fingerprint: desired.spec_fingerprint,
        });

        assert!(open_item20_session(&mut store, &provider, &identity, "unused").is_err());
        assert_eq!(provider.create_calls.get(), 0);
        assert!(matches!(store.state, AcceptanceVmLifecycleState::Empty));
    }

    #[test]
    fn endpoint_is_resolved_only_after_exact_bound_target_verification() {
        let mut store = MemoryStore::new(&identity());
        let provider = FakeProvider::default();
        let opened = open_once(&mut store, &provider);
        assert_eq!(
            verified_item20_endpoint(&provider, &identity(), &opened.binding).unwrap(),
            Ipv4Addr::new(1, 1, 1, 1)
        );
    }

    #[test]
    fn close_deletes_exact_bound_target_and_terminalizes() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let provider = FakeProvider::default();
        let opened = open_once(&mut store, &provider);
        assert_eq!(
            close_item20_session(&mut store, &provider, &identity).unwrap(),
            SessionCloseOutcome::DeletedAndTerminal
        );
        assert_eq!(provider.delete_calls.get(), 1);
        assert!(provider.observed.borrow().is_empty());
        assert_eq!(
            store.state,
            AcceptanceVmLifecycleState::Terminal {
                last_generation: opened.binding.generation
            }
        );
    }

    #[test]
    fn dispatched_delete_recovers_when_provider_target_is_already_absent() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let binding = VmBinding {
            intent: identity.ownership_intent().unwrap(),
            provider_id: ProviderResourceId::new(PROVIDER_ID).unwrap(),
            generation: Generation::INITIAL,
        };
        store.state = AcceptanceVmLifecycleState::DeleteDispatched(binding.clone());
        let provider = FakeProvider::default();

        assert_eq!(
            close_item20_session(&mut store, &provider, &identity).unwrap(),
            SessionCloseOutcome::DeletedAndTerminal
        );
        assert_eq!(provider.delete_calls.get(), 0);
        assert_eq!(
            store.state,
            AcceptanceVmLifecycleState::Terminal {
                last_generation: binding.generation
            }
        );
    }

    #[test]
    fn terminal_session_cannot_be_reopened() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        store.state = AcceptanceVmLifecycleState::Terminal {
            last_generation: Generation::INITIAL,
        };
        let provider = FakeProvider::default();
        assert!(open_item20_session(&mut store, &provider, &identity, "unused").is_err());
        assert_eq!(provider.create_calls.get(), 0);
    }

    #[test]
    fn close_empty_session_does_not_mutate_provider() {
        let identity = identity();
        let mut store = MemoryStore::new(&identity);
        let provider = FakeProvider::default();
        assert_eq!(
            close_item20_session(&mut store, &provider, &identity).unwrap(),
            SessionCloseOutcome::NoResourceCreated
        );
        assert_eq!(provider.delete_calls.get(), 0);
    }
}
