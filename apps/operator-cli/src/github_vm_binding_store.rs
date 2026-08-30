use proxy_core::{
    Generation, LifecycleScope, OwnershipIntent, ProviderResourceId, VmBinding, VmBindingStore,
    OWNERSHIP_MANAGER, OWNERSHIP_PROJECT,
};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::BTreeSet;
use std::fmt;
use std::time::Duration;
use uuid::Uuid;

const CANONICAL_REPOSITORY: &str = "iamaman11/mobile-proxy";
const GITHUB_API_BASE: &str = "https://api.github.com";
const GITHUB_API_VERSION: &str = "2022-11-28";
const DEPLOYMENT_TASK: &str = "mobile-proxy:acceptance-vm-binding";
const DEPLOYMENT_ENVIRONMENT: &str = "acceptance-vm-binding-state";
const LEDGER_FORMAT_VERSION: u64 = 2;
const PAGE_SIZE: u32 = 100;
const MAX_LEDGER_PAGES: u32 = 100;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum LedgerTransition {
    PrepareCreate,
    DispatchCreate,
    Bind,
    Replace,
    PrepareDelete,
    DispatchDelete,
    Clear,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct BindingPayload {
    provider_id: String,
    generation: u64,
}

impl BindingPayload {
    fn from_binding(binding: &VmBinding) -> Self {
        Self {
            provider_id: binding.provider_id.as_str().to_owned(),
            generation: binding.generation.get(),
        }
    }

    fn to_binding(&self, intent: &OwnershipIntent) -> Result<VmBinding, BindingStoreError> {
        validate_provider_uuid(&self.provider_id)?;
        Ok(VmBinding {
            intent: intent.clone(),
            provider_id: ProviderResourceId::new(self.provider_id.clone())
                .map_err(|_| BindingStoreError::InvalidLedgerRecord)?,
            generation: Generation::new(self.generation)
                .map_err(|_| BindingStoreError::InvalidLedgerRecord)?,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct GitHubDeploymentPayload {
    format_version: u64,
    project: String,
    managed_by: String,
    candidate_sha: String,
    scope: LifecycleScope,
    intent_id: String,
    predecessor_deployment_id: Option<u64>,
    transition: LedgerTransition,
    generation: u64,
    expected: Option<BindingPayload>,
    replacement: Option<BindingPayload>,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize)]
struct DeploymentRecord {
    id: u64,
    sha: String,
    #[serde(rename = "ref")]
    git_ref: String,
    task: String,
    environment: String,
    payload: GitHubDeploymentPayload,
}

#[derive(Clone, Debug)]
struct NewDeploymentRecord {
    candidate_sha: String,
    payload: GitHubDeploymentPayload,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AcceptanceVmLifecycleState {
    Empty,
    CreatePrepared { generation: Generation },
    CreateDispatched { generation: Generation },
    Bound(VmBinding),
    DeletePrepared(VmBinding),
    DeleteDispatched(VmBinding),
    Terminal { last_generation: Generation },
}

impl AcceptanceVmLifecycleState {
    fn binding(&self) -> Option<&VmBinding> {
        match self {
            Self::Bound(binding) | Self::DeletePrepared(binding) | Self::DeleteDispatched(binding) => {
                Some(binding)
            }
            Self::Empty
            | Self::CreatePrepared { .. }
            | Self::CreateDispatched { .. }
            | Self::Terminal { .. } => None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct LedgerState {
    head_id: Option<u64>,
    phase: AcceptanceVmLifecycleState,
}

pub struct DurableGitHubVmBindingStore {
    inner: BindingStore<GitHubDeploymentApi>,
}

impl DurableGitHubVmBindingStore {
    pub fn new(github_token: String, candidate_sha: String) -> Result<Self, BindingStoreError> {
        validate_candidate_sha(&candidate_sha)?;
        Ok(Self {
            inner: BindingStore {
                backend: GitHubDeploymentApi::new(github_token)?,
                candidate_sha,
            },
        })
    }

    pub fn lifecycle_state(
        &self,
        intent: &OwnershipIntent,
    ) -> Result<AcceptanceVmLifecycleState, BindingStoreError> {
        self.inner.lifecycle_state(intent)
    }

    pub fn prepare_create(
        &mut self,
        intent: &OwnershipIntent,
    ) -> Result<Generation, BindingStoreError> {
        self.inner.prepare_create(intent)
    }

    pub fn mark_create_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        generation: Generation,
    ) -> Result<(), BindingStoreError> {
        self.inner.mark_create_dispatched(intent, generation)
    }

    pub fn prepare_delete(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> Result<(), BindingStoreError> {
        self.inner.prepare_delete(intent, binding)
    }

    pub fn mark_delete_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> Result<(), BindingStoreError> {
        self.inner.mark_delete_dispatched(intent, binding)
    }
}

impl VmBindingStore for DurableGitHubVmBindingStore {
    type Error = BindingStoreError;

    fn load(&self, intent: &OwnershipIntent) -> Result<Option<VmBinding>, Self::Error> {
        self.inner.load(intent)
    }

    fn compare_and_swap(
        &mut self,
        intent: &OwnershipIntent,
        expected: Option<&VmBinding>,
        replacement: Option<VmBinding>,
    ) -> Result<(), Self::Error> {
        self.inner.compare_and_swap(intent, expected, replacement)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BindingStoreError {
    InvalidCandidateSha,
    InvalidOwnershipIntent,
    InvalidProviderUuid,
    InvalidLedgerRecord,
    ForkedLedger,
    LedgerTooLarge,
    CompareAndSwapConflict,
    TerminalIntentReuse,
    OperationInProgress,
    CreateAlreadyDispatched,
    DeleteAlreadyDispatched,
    InvalidTransition,
    HttpTransport,
    HttpStatus(u16),
    WriteVerificationFailed,
}

impl fmt::Display for BindingStoreError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidCandidateSha => formatter.write_str("invalid immutable candidate SHA"),
            Self::InvalidOwnershipIntent => {
                formatter.write_str("binding store requires exact acceptance candidate intent")
            }
            Self::InvalidProviderUuid => {
                formatter.write_str("binding store provider identity is not a canonical UUID")
            }
            Self::InvalidLedgerRecord => {
                formatter.write_str("GitHub deployment binding ledger contains an invalid record")
            }
            Self::ForkedLedger => {
                formatter.write_str("GitHub deployment binding ledger is forked or non-linear")
            }
            Self::LedgerTooLarge => {
                formatter.write_str("GitHub deployment binding ledger exceeds bound")
            }
            Self::CompareAndSwapConflict => formatter.write_str("binding compare-and-swap conflict"),
            Self::TerminalIntentReuse => {
                formatter.write_str("cleared ownership intent is terminal and cannot be reused")
            }
            Self::OperationInProgress => {
                formatter.write_str("acceptance VM lifecycle operation is in progress")
            }
            Self::CreateAlreadyDispatched => formatter.write_str(
                "create dispatch was already durably fenced and must not be sent again",
            ),
            Self::DeleteAlreadyDispatched => formatter.write_str(
                "delete dispatch was already durably fenced and must be recovered by exact target state",
            ),
            Self::InvalidTransition => formatter.write_str("invalid binding state transition"),
            Self::HttpTransport => formatter.write_str("GitHub deployment-state transport failed"),
            Self::HttpStatus(status) => {
                write!(formatter, "GitHub deployment-state HTTP status {status}")
            }
            Self::WriteVerificationFailed => {
                formatter.write_str("GitHub deployment-state write could not be verified")
            }
        }
    }
}

impl std::error::Error for BindingStoreError {}

trait DeploymentBackend {
    fn list_records(&self, candidate_sha: &str) -> Result<Vec<DeploymentRecord>, BindingStoreError>;

    fn append_record(
        &self,
        record: NewDeploymentRecord,
    ) -> Result<DeploymentRecord, BindingStoreError>;
}

struct BindingStore<B> {
    backend: B,
    candidate_sha: String,
}

impl<B: DeploymentBackend> BindingStore<B> {
    fn validate_intent(&self, intent: &OwnershipIntent) -> Result<(), BindingStoreError> {
        if intent.scope() != LifecycleScope::Acceptance
            || intent.id() != format!("candidate:{}", self.candidate_sha)
        {
            return Err(BindingStoreError::InvalidOwnershipIntent);
        }
        Ok(())
    }

    fn validate_binding(&self, binding: &VmBinding) -> Result<(), BindingStoreError> {
        self.validate_intent(&binding.intent)?;
        validate_provider_uuid(binding.provider_id.as_str())
    }

    fn current_state(&self, intent: &OwnershipIntent) -> Result<LedgerState, BindingStoreError> {
        self.validate_intent(intent)?;
        reconstruct_ledger(
            self.backend.list_records(&self.candidate_sha)?,
            &self.candidate_sha,
        )
    }

    fn lifecycle_state(
        &self,
        intent: &OwnershipIntent,
    ) -> Result<AcceptanceVmLifecycleState, BindingStoreError> {
        Ok(self.current_state(intent)?.phase)
    }

    fn append_transition(
        &self,
        intent: &OwnershipIntent,
        before: &LedgerState,
        transition: LedgerTransition,
        generation: Generation,
        expected: Option<&VmBinding>,
        replacement: Option<&VmBinding>,
        expected_after: AcceptanceVmLifecycleState,
    ) -> Result<(), BindingStoreError> {
        let payload = GitHubDeploymentPayload {
            format_version: LEDGER_FORMAT_VERSION,
            project: OWNERSHIP_PROJECT.to_owned(),
            managed_by: OWNERSHIP_MANAGER.to_owned(),
            candidate_sha: self.candidate_sha.clone(),
            scope: LifecycleScope::Acceptance,
            intent_id: intent.id().to_owned(),
            predecessor_deployment_id: before.head_id,
            transition,
            generation: generation.get(),
            expected: expected.map(BindingPayload::from_binding),
            replacement: replacement.map(BindingPayload::from_binding),
        };
        let created = self.backend.append_record(NewDeploymentRecord {
            candidate_sha: self.candidate_sha.clone(),
            payload,
        })?;
        let after = self.current_state(intent)?;
        if after.head_id != Some(created.id) || after.phase != expected_after {
            return Err(BindingStoreError::WriteVerificationFailed);
        }
        Ok(())
    }

    fn prepare_create(
        &mut self,
        intent: &OwnershipIntent,
    ) -> Result<Generation, BindingStoreError> {
        let before = self.current_state(intent)?;
        match before.phase {
            AcceptanceVmLifecycleState::Empty => {
                let generation = Generation::INITIAL;
                self.append_transition(
                    intent,
                    &before,
                    LedgerTransition::PrepareCreate,
                    generation,
                    None,
                    None,
                    AcceptanceVmLifecycleState::CreatePrepared { generation },
                )?;
                Ok(generation)
            }
            AcceptanceVmLifecycleState::Terminal { .. } => Err(BindingStoreError::TerminalIntentReuse),
            _ => Err(BindingStoreError::OperationInProgress),
        }
    }

    fn mark_create_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        generation: Generation,
    ) -> Result<(), BindingStoreError> {
        let before = self.current_state(intent)?;
        match before.phase {
            AcceptanceVmLifecycleState::CreatePrepared {
                generation: prepared_generation,
            } if prepared_generation == generation => self.append_transition(
                intent,
                &before,
                LedgerTransition::DispatchCreate,
                generation,
                None,
                None,
                AcceptanceVmLifecycleState::CreateDispatched { generation },
            ),
            AcceptanceVmLifecycleState::CreateDispatched {
                generation: dispatched_generation,
            } if dispatched_generation == generation => Err(BindingStoreError::CreateAlreadyDispatched),
            AcceptanceVmLifecycleState::Terminal { .. } => Err(BindingStoreError::TerminalIntentReuse),
            _ => Err(BindingStoreError::InvalidTransition),
        }
    }

    fn prepare_delete(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> Result<(), BindingStoreError> {
        self.validate_binding(binding)?;
        let before = self.current_state(intent)?;
        match &before.phase {
            AcceptanceVmLifecycleState::Bound(current) if current == binding => self.append_transition(
                intent,
                &before,
                LedgerTransition::PrepareDelete,
                binding.generation,
                Some(binding),
                None,
                AcceptanceVmLifecycleState::DeletePrepared(binding.clone()),
            ),
            AcceptanceVmLifecycleState::Terminal { .. } => Err(BindingStoreError::TerminalIntentReuse),
            AcceptanceVmLifecycleState::Bound(_) => Err(BindingStoreError::CompareAndSwapConflict),
            _ => Err(BindingStoreError::OperationInProgress),
        }
    }

    fn mark_delete_dispatched(
        &mut self,
        intent: &OwnershipIntent,
        binding: &VmBinding,
    ) -> Result<(), BindingStoreError> {
        self.validate_binding(binding)?;
        let before = self.current_state(intent)?;
        match &before.phase {
            AcceptanceVmLifecycleState::DeletePrepared(current) if current == binding => {
                self.append_transition(
                    intent,
                    &before,
                    LedgerTransition::DispatchDelete,
                    binding.generation,
                    Some(binding),
                    None,
                    AcceptanceVmLifecycleState::DeleteDispatched(binding.clone()),
                )
            }
            AcceptanceVmLifecycleState::DeleteDispatched(current) if current == binding => {
                Err(BindingStoreError::DeleteAlreadyDispatched)
            }
            AcceptanceVmLifecycleState::Terminal { .. } => Err(BindingStoreError::TerminalIntentReuse),
            _ => Err(BindingStoreError::InvalidTransition),
        }
    }
}

impl<B: DeploymentBackend> VmBindingStore for BindingStore<B> {
    type Error = BindingStoreError;

    fn load(&self, intent: &OwnershipIntent) -> Result<Option<VmBinding>, Self::Error> {
        match self.current_state(intent)?.phase {
            AcceptanceVmLifecycleState::Empty => Ok(None),
            AcceptanceVmLifecycleState::Bound(binding) => Ok(Some(binding)),
            AcceptanceVmLifecycleState::Terminal { .. } => Err(BindingStoreError::TerminalIntentReuse),
            AcceptanceVmLifecycleState::CreatePrepared { .. }
            | AcceptanceVmLifecycleState::CreateDispatched { .. }
            | AcceptanceVmLifecycleState::DeletePrepared(_)
            | AcceptanceVmLifecycleState::DeleteDispatched(_) => Err(BindingStoreError::OperationInProgress),
        }
    }

    fn compare_and_swap(
        &mut self,
        intent: &OwnershipIntent,
        expected: Option<&VmBinding>,
        replacement: Option<VmBinding>,
    ) -> Result<(), Self::Error> {
        self.validate_intent(intent)?;
        if let Some(binding) = expected {
            self.validate_binding(binding)?;
        }
        if let Some(binding) = replacement.as_ref() {
            self.validate_binding(binding)?;
        }

        let before = self.current_state(intent)?;
        if matches!(before.phase, AcceptanceVmLifecycleState::Terminal { .. }) {
            return Err(BindingStoreError::TerminalIntentReuse);
        }

        match (expected, replacement.as_ref()) {
            (None, Some(new_binding)) => match before.phase {
                AcceptanceVmLifecycleState::CreateDispatched { generation }
                    if generation == new_binding.generation => self.append_transition(
                        intent,
                        &before,
                        LedgerTransition::Bind,
                        generation,
                        None,
                        Some(new_binding),
                        AcceptanceVmLifecycleState::Bound(new_binding.clone()),
                    ),
                AcceptanceVmLifecycleState::CreatePrepared { .. } => {
                    Err(BindingStoreError::InvalidTransition)
                }
                AcceptanceVmLifecycleState::Empty => Err(BindingStoreError::InvalidTransition),
                _ => Err(BindingStoreError::OperationInProgress),
            },
            (Some(old_binding), Some(new_binding)) => match &before.phase {
                AcceptanceVmLifecycleState::Bound(current) if current == old_binding => {
                    let next = old_binding
                        .generation
                        .next()
                        .map_err(|_| BindingStoreError::InvalidTransition)?;
                    if new_binding.intent != old_binding.intent
                        || new_binding.provider_id == old_binding.provider_id
                        || new_binding.generation != next
                    {
                        return Err(BindingStoreError::InvalidTransition);
                    }
                    self.append_transition(
                        intent,
                        &before,
                        LedgerTransition::Replace,
                        new_binding.generation,
                        Some(old_binding),
                        Some(new_binding),
                        AcceptanceVmLifecycleState::Bound(new_binding.clone()),
                    )
                }
                AcceptanceVmLifecycleState::Bound(_) => Err(BindingStoreError::CompareAndSwapConflict),
                _ => Err(BindingStoreError::OperationInProgress),
            },
            (Some(old_binding), None) => match &before.phase {
                AcceptanceVmLifecycleState::DeleteDispatched(current) if current == old_binding => {
                    self.append_transition(
                        intent,
                        &before,
                        LedgerTransition::Clear,
                        old_binding.generation,
                        Some(old_binding),
                        None,
                        AcceptanceVmLifecycleState::Terminal {
                            last_generation: old_binding.generation,
                        },
                    )
                }
                AcceptanceVmLifecycleState::Bound(current) if current != old_binding => {
                    Err(BindingStoreError::CompareAndSwapConflict)
                }
                _ => Err(BindingStoreError::InvalidTransition),
            },
            (None, None) => Err(BindingStoreError::InvalidTransition),
        }
    }
}

fn reconstruct_ledger(
    mut records: Vec<DeploymentRecord>,
    candidate_sha: &str,
) -> Result<LedgerState, BindingStoreError> {
    validate_candidate_sha(candidate_sha)?;
    records.sort_by_key(|record| record.id);

    let intent = OwnershipIntent::new(
        LifecycleScope::Acceptance,
        format!("candidate:{candidate_sha}"),
    )
    .map_err(|_| BindingStoreError::InvalidOwnershipIntent)?;
    let mut seen_ids = BTreeSet::new();
    let mut state = LedgerState {
        head_id: None,
        phase: AcceptanceVmLifecycleState::Empty,
    };

    for record in records {
        if !seen_ids.insert(record.id) {
            return Err(BindingStoreError::ForkedLedger);
        }
        validate_record(&record, candidate_sha, &intent)?;
        if record.payload.predecessor_deployment_id != state.head_id {
            return Err(BindingStoreError::ForkedLedger);
        }
        state.phase = apply_record(&state.phase, &record.payload, &intent)?;
        state.head_id = Some(record.id);
    }

    Ok(state)
}

fn apply_record(
    phase: &AcceptanceVmLifecycleState,
    payload: &GitHubDeploymentPayload,
    intent: &OwnershipIntent,
) -> Result<AcceptanceVmLifecycleState, BindingStoreError> {
    let generation = Generation::new(payload.generation)
        .map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
    let expected_binding = payload
        .expected
        .as_ref()
        .map(|binding| binding.to_binding(intent))
        .transpose()?;
    let replacement_binding = payload
        .replacement
        .as_ref()
        .map(|binding| binding.to_binding(intent))
        .transpose()?;

    match payload.transition {
        LedgerTransition::PrepareCreate => {
            if !matches!(phase, AcceptanceVmLifecycleState::Empty)
                || generation != Generation::INITIAL
                || expected_binding.is_some()
                || replacement_binding.is_some()
            {
                return Err(BindingStoreError::InvalidTransition);
            }
            Ok(AcceptanceVmLifecycleState::CreatePrepared { generation })
        }
        LedgerTransition::DispatchCreate => match phase {
            AcceptanceVmLifecycleState::CreatePrepared {
                generation: prepared_generation,
            } if *prepared_generation == generation
                && expected_binding.is_none()
                && replacement_binding.is_none() => {
                    Ok(AcceptanceVmLifecycleState::CreateDispatched { generation })
                }
            _ => Err(BindingStoreError::InvalidTransition),
        },
        LedgerTransition::Bind => match phase {
            AcceptanceVmLifecycleState::CreateDispatched {
                generation: dispatched_generation,
            } if *dispatched_generation == generation && expected_binding.is_none() => {
                let binding = replacement_binding.ok_or(BindingStoreError::InvalidTransition)?;
                if binding.generation != generation {
                    return Err(BindingStoreError::InvalidTransition);
                }
                Ok(AcceptanceVmLifecycleState::Bound(binding))
            }
            _ => Err(BindingStoreError::InvalidTransition),
        },
        LedgerTransition::Replace => match phase {
            AcceptanceVmLifecycleState::Bound(current) => {
                let expected = expected_binding.ok_or(BindingStoreError::InvalidTransition)?;
                let replacement = replacement_binding.ok_or(BindingStoreError::InvalidTransition)?;
                let next = current
                    .generation
                    .next()
                    .map_err(|_| BindingStoreError::InvalidTransition)?;
                if &expected != current
                    || replacement.intent != current.intent
                    || replacement.provider_id == current.provider_id
                    || replacement.generation != next
                    || generation != next
                {
                    return Err(BindingStoreError::InvalidTransition);
                }
                Ok(AcceptanceVmLifecycleState::Bound(replacement))
            }
            _ => Err(BindingStoreError::InvalidTransition),
        },
        LedgerTransition::PrepareDelete => match phase {
            AcceptanceVmLifecycleState::Bound(current) => {
                let expected = expected_binding.ok_or(BindingStoreError::InvalidTransition)?;
                if &expected != current
                    || generation != current.generation
                    || replacement_binding.is_some()
                {
                    return Err(BindingStoreError::InvalidTransition);
                }
                Ok(AcceptanceVmLifecycleState::DeletePrepared(current.clone()))
            }
            _ => Err(BindingStoreError::InvalidTransition),
        },
        LedgerTransition::DispatchDelete => match phase {
            AcceptanceVmLifecycleState::DeletePrepared(current) => {
                let expected = expected_binding.ok_or(BindingStoreError::InvalidTransition)?;
                if &expected != current
                    || generation != current.generation
                    || replacement_binding.is_some()
                {
                    return Err(BindingStoreError::InvalidTransition);
                }
                Ok(AcceptanceVmLifecycleState::DeleteDispatched(current.clone()))
            }
            _ => Err(BindingStoreError::InvalidTransition),
        },
        LedgerTransition::Clear => match phase {
            AcceptanceVmLifecycleState::DeleteDispatched(current) => {
                let expected = expected_binding.ok_or(BindingStoreError::InvalidTransition)?;
                if &expected != current
                    || generation != current.generation
                    || replacement_binding.is_some()
                {
                    return Err(BindingStoreError::InvalidTransition);
                }
                Ok(AcceptanceVmLifecycleState::Terminal {
                    last_generation: current.generation,
                })
            }
            _ => Err(BindingStoreError::InvalidTransition),
        },
    }
}

fn validate_record(
    record: &DeploymentRecord,
    candidate_sha: &str,
    intent: &OwnershipIntent,
) -> Result<(), BindingStoreError> {
    let payload = &record.payload;
    if record.sha != candidate_sha
        || record.git_ref != candidate_sha
        || record.task != DEPLOYMENT_TASK
        || record.environment != DEPLOYMENT_ENVIRONMENT
        || payload.format_version != LEDGER_FORMAT_VERSION
        || payload.project != OWNERSHIP_PROJECT
        || payload.managed_by != OWNERSHIP_MANAGER
        || payload.candidate_sha != candidate_sha
        || payload.scope != LifecycleScope::Acceptance
        || payload.intent_id != intent.id()
    {
        return Err(BindingStoreError::InvalidLedgerRecord);
    }

    Generation::new(payload.generation).map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
    for binding in [payload.expected.as_ref(), payload.replacement.as_ref()]
        .into_iter()
        .flatten()
    {
        validate_provider_uuid(&binding.provider_id)?;
        Generation::new(binding.generation)
            .map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
    }
    Ok(())
}

fn validate_candidate_sha(candidate_sha: &str) -> Result<(), BindingStoreError> {
    if candidate_sha.len() != 40
        || !candidate_sha
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(BindingStoreError::InvalidCandidateSha);
    }
    Ok(())
}

fn validate_provider_uuid(provider_id: &str) -> Result<(), BindingStoreError> {
    let parsed = Uuid::parse_str(provider_id).map_err(|_| BindingStoreError::InvalidProviderUuid)?;
    if parsed.to_string() != provider_id {
        return Err(BindingStoreError::InvalidProviderUuid);
    }
    Ok(())
}

struct GitHubDeploymentApi {
    client: Client,
    token: String,
}

impl GitHubDeploymentApi {
    fn new(token: String) -> Result<Self, BindingStoreError> {
        if token.is_empty() {
            return Err(BindingStoreError::HttpTransport);
        }
        Ok(Self {
            client: Client::builder()
                .timeout(Duration::from_secs(20))
                .build()
                .map_err(|_| BindingStoreError::HttpTransport)?,
            token,
        })
    }

    fn deployments_url(&self) -> String {
        format!("{GITHUB_API_BASE}/repos/{CANONICAL_REPOSITORY}/deployments")
    }

    fn request(&self, method: reqwest::Method) -> reqwest::blocking::RequestBuilder {
        self.client
            .request(method, self.deployments_url())
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", GITHUB_API_VERSION)
            .header("User-Agent", "mobile-proxy-operator-cli")
    }
}

impl DeploymentBackend for GitHubDeploymentApi {
    fn list_records(&self, candidate_sha: &str) -> Result<Vec<DeploymentRecord>, BindingStoreError> {
        let mut records = Vec::new();
        for page in 1..=MAX_LEDGER_PAGES {
            let query = [
                ("ref", candidate_sha.to_owned()),
                ("task", DEPLOYMENT_TASK.to_owned()),
                ("environment", DEPLOYMENT_ENVIRONMENT.to_owned()),
                ("per_page", PAGE_SIZE.to_string()),
                ("page", page.to_string()),
            ];
            let response = self
                .request(reqwest::Method::GET)
                .query(&query)
                .send()
                .map_err(|_| BindingStoreError::HttpTransport)?;
            if response.status() != reqwest::StatusCode::OK {
                return Err(BindingStoreError::HttpStatus(response.status().as_u16()));
            }
            let page_records: Vec<DeploymentRecord> = response
                .json()
                .map_err(|_| BindingStoreError::HttpTransport)?;
            let page_len = page_records.len();
            records.extend(page_records);
            if page_len < PAGE_SIZE as usize {
                return Ok(records);
            }
        }
        Err(BindingStoreError::LedgerTooLarge)
    }

    fn append_record(
        &self,
        record: NewDeploymentRecord,
    ) -> Result<DeploymentRecord, BindingStoreError> {
        let response = self
            .request(reqwest::Method::POST)
            .json(&json!({
                "ref": record.candidate_sha,
                "task": DEPLOYMENT_TASK,
                "auto_merge": false,
                "required_contexts": [],
                "payload": record.payload,
                "environment": DEPLOYMENT_ENVIRONMENT,
                "description": "mobile-proxy durable acceptance VM lifecycle state",
                "transient_environment": true,
                "production_environment": false
            }))
            .send()
            .map_err(|_| BindingStoreError::HttpTransport)?;
        if response.status() != reqwest::StatusCode::CREATED {
            return Err(BindingStoreError::HttpStatus(response.status().as_u16()));
        }
        response
            .json()
            .map_err(|_| BindingStoreError::HttpTransport)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::rc::Rc;

    const SHA: &str = "0123456789abcdef0123456789abcdef01234567";
    const ID1: &str = "11111111-1111-4111-8111-111111111111";
    const ID2: &str = "22222222-2222-4222-8222-222222222222";
    const ID3: &str = "33333333-3333-4333-8333-333333333333";

    #[derive(Clone, Default)]
    struct MemoryBackend {
        records: Rc<RefCell<Vec<DeploymentRecord>>>,
    }

    impl DeploymentBackend for MemoryBackend {
        fn list_records(
            &self,
            _candidate_sha: &str,
        ) -> Result<Vec<DeploymentRecord>, BindingStoreError> {
            Ok(self.records.borrow().clone())
        }

        fn append_record(
            &self,
            record: NewDeploymentRecord,
        ) -> Result<DeploymentRecord, BindingStoreError> {
            let mut records = self.records.borrow_mut();
            let created = DeploymentRecord {
                id: records.last().map_or(1, |last| last.id + 1),
                sha: record.candidate_sha.clone(),
                git_ref: record.candidate_sha,
                task: DEPLOYMENT_TASK.to_owned(),
                environment: DEPLOYMENT_ENVIRONMENT.to_owned(),
                payload: record.payload,
            };
            records.push(created.clone());
            Ok(created)
        }
    }

    fn intent() -> OwnershipIntent {
        OwnershipIntent::new(LifecycleScope::Acceptance, format!("candidate:{SHA}")).unwrap()
    }

    fn binding(id: &str, generation: u64) -> VmBinding {
        VmBinding {
            intent: intent(),
            provider_id: ProviderResourceId::new(id).unwrap(),
            generation: Generation::new(generation).unwrap(),
        }
    }

    fn store(backend: MemoryBackend) -> BindingStore<MemoryBackend> {
        BindingStore {
            backend,
            candidate_sha: SHA.to_owned(),
        }
    }

    fn bind_first(store: &mut BindingStore<MemoryBackend>) -> VmBinding {
        let generation = store.prepare_create(&intent()).unwrap();
        store.mark_create_dispatched(&intent(), generation).unwrap();
        let first = binding(ID1, generation.get());
        store
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();
        first
    }

    #[test]
    fn create_prepare_and_dispatch_survive_restart_without_reopening_post() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let generation = writer.prepare_create(&intent()).unwrap();
        writer.mark_create_dispatched(&intent(), generation).unwrap();
        drop(writer);

        let mut restarted = store(backend);
        assert_eq!(
            restarted.lifecycle_state(&intent()).unwrap(),
            AcceptanceVmLifecycleState::CreateDispatched { generation }
        );
        assert_eq!(restarted.load(&intent()), Err(BindingStoreError::OperationInProgress));
        assert_eq!(
            restarted.mark_create_dispatched(&intent(), generation),
            Err(BindingStoreError::CreateAlreadyDispatched)
        );
    }

    #[test]
    fn binding_cannot_be_committed_before_create_dispatch_fence() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend);
        let generation = writer.prepare_create(&intent()).unwrap();
        assert_eq!(
            writer.compare_and_swap(&intent(), None, Some(binding(ID1, generation.get()))),
            Err(BindingStoreError::InvalidTransition)
        );
    }

    #[test]
    fn dispatched_create_can_recover_by_committing_exact_observed_provider_id() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let generation = writer.prepare_create(&intent()).unwrap();
        writer.mark_create_dispatched(&intent(), generation).unwrap();
        drop(writer);

        let mut restarted = store(backend.clone());
        let first = binding(ID1, generation.get());
        restarted
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();
        drop(restarted);

        assert_eq!(store(backend).load(&intent()).unwrap(), Some(first));
    }

    #[test]
    fn stale_compare_and_swap_is_rejected_without_appending() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let first = bind_first(&mut writer);
        let before = backend.records.borrow().len();

        assert_eq!(
            writer.compare_and_swap(&intent(), Some(&binding(ID2, 1)), Some(binding(ID3, 2))),
            Err(BindingStoreError::CompareAndSwapConflict)
        );
        assert_eq!(backend.records.borrow().len(), before);
        assert_eq!(writer.load(&intent()).unwrap(), Some(first));
    }

    #[test]
    fn replacement_requires_exact_next_generation_and_new_provider_id() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend);
        let first = bind_first(&mut writer);

        assert_eq!(
            writer.compare_and_swap(&intent(), Some(&first), Some(binding(ID2, 3))),
            Err(BindingStoreError::InvalidTransition)
        );
        assert_eq!(
            writer.compare_and_swap(&intent(), Some(&first), Some(binding(ID1, 2))),
            Err(BindingStoreError::InvalidTransition)
        );

        let second = binding(ID2, 2);
        writer
            .compare_and_swap(&intent(), Some(&first), Some(second.clone()))
            .unwrap();
        assert_eq!(writer.load(&intent()).unwrap(), Some(second));
    }

    #[test]
    fn delete_requires_prepare_dispatch_then_terminal_clear() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let first = bind_first(&mut writer);

        assert_eq!(
            writer.compare_and_swap(&intent(), Some(&first), None),
            Err(BindingStoreError::InvalidTransition)
        );
        writer.prepare_delete(&intent(), &first).unwrap();
        assert_eq!(writer.load(&intent()), Err(BindingStoreError::OperationInProgress));
        writer.mark_delete_dispatched(&intent(), &first).unwrap();
        assert_eq!(
            writer.mark_delete_dispatched(&intent(), &first),
            Err(BindingStoreError::DeleteAlreadyDispatched)
        );
        writer
            .compare_and_swap(&intent(), Some(&first), None)
            .unwrap();
        drop(writer);

        let mut restarted = store(backend);
        assert_eq!(
            restarted.lifecycle_state(&intent()).unwrap(),
            AcceptanceVmLifecycleState::Terminal {
                last_generation: first.generation,
            }
        );
        assert_eq!(
            restarted.load(&intent()),
            Err(BindingStoreError::TerminalIntentReuse)
        );
        assert_eq!(
            restarted.prepare_create(&intent()),
            Err(BindingStoreError::TerminalIntentReuse)
        );
    }

    #[test]
    fn forked_deployment_history_fails_closed() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let generation = writer.prepare_create(&intent()).unwrap();
        let predecessor = backend.records.borrow()[0].id;

        for id in [2, 3] {
            backend.records.borrow_mut().push(DeploymentRecord {
                id,
                sha: SHA.to_owned(),
                git_ref: SHA.to_owned(),
                task: DEPLOYMENT_TASK.to_owned(),
                environment: DEPLOYMENT_ENVIRONMENT.to_owned(),
                payload: GitHubDeploymentPayload {
                    format_version: LEDGER_FORMAT_VERSION,
                    project: OWNERSHIP_PROJECT.to_owned(),
                    managed_by: OWNERSHIP_MANAGER.to_owned(),
                    candidate_sha: SHA.to_owned(),
                    scope: LifecycleScope::Acceptance,
                    intent_id: intent().id().to_owned(),
                    predecessor_deployment_id: Some(predecessor),
                    transition: LedgerTransition::DispatchCreate,
                    generation: generation.get(),
                    expected: None,
                    replacement: None,
                },
            });
        }

        assert_eq!(
            store(backend).lifecycle_state(&intent()),
            Err(BindingStoreError::ForkedLedger)
        );
    }

    #[test]
    fn production_or_wrong_candidate_intent_is_rejected() {
        let store = store(MemoryBackend::default());
        let production =
            OwnershipIntent::new(LifecycleScope::Production, format!("candidate:{SHA}")).unwrap();
        assert_eq!(
            store.load(&production),
            Err(BindingStoreError::InvalidOwnershipIntent)
        );

        let wrong = OwnershipIntent::new(
            LifecycleScope::Acceptance,
            "candidate:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        .unwrap();
        assert_eq!(
            store.load(&wrong),
            Err(BindingStoreError::InvalidOwnershipIntent)
        );
    }

    #[test]
    fn non_canonical_uuid_is_rejected_before_persistence() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let generation = writer.prepare_create(&intent()).unwrap();
        writer.mark_create_dispatched(&intent(), generation).unwrap();
        let invalid = VmBinding {
            intent: intent(),
            provider_id: ProviderResourceId::new("NOT-A-VULTR-UUID").unwrap(),
            generation,
        };
        let before = backend.records.borrow().len();
        assert_eq!(
            writer.compare_and_swap(&intent(), None, Some(invalid)),
            Err(BindingStoreError::InvalidProviderUuid)
        );
        assert_eq!(backend.records.borrow().len(), before);
    }

    #[test]
    fn malformed_history_after_terminal_is_rejected() {
        let backend = MemoryBackend::default();
        let mut writer = store(backend.clone());
        let first = bind_first(&mut writer);
        writer.prepare_delete(&intent(), &first).unwrap();
        writer.mark_delete_dispatched(&intent(), &first).unwrap();
        writer
            .compare_and_swap(&intent(), Some(&first), None)
            .unwrap();

        let predecessor = backend.records.borrow().last().unwrap().id;
        backend.records.borrow_mut().push(DeploymentRecord {
            id: predecessor + 1,
            sha: SHA.to_owned(),
            git_ref: SHA.to_owned(),
            task: DEPLOYMENT_TASK.to_owned(),
            environment: DEPLOYMENT_ENVIRONMENT.to_owned(),
            payload: GitHubDeploymentPayload {
                format_version: LEDGER_FORMAT_VERSION,
                project: OWNERSHIP_PROJECT.to_owned(),
                managed_by: OWNERSHIP_MANAGER.to_owned(),
                candidate_sha: SHA.to_owned(),
                scope: LifecycleScope::Acceptance,
                intent_id: intent().id().to_owned(),
                predecessor_deployment_id: Some(predecessor),
                transition: LedgerTransition::PrepareCreate,
                generation: Generation::INITIAL.get(),
                expected: None,
                replacement: None,
            },
        });

        assert_eq!(
            store(backend).lifecycle_state(&intent()),
            Err(BindingStoreError::InvalidTransition)
        );
    }
}
