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
const LEDGER_FORMAT_VERSION: u64 = 1;
const MAX_LEDGER_PAGES: u32 = 100;
const PAGE_SIZE: u32 = 100;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum LedgerTransition {
    Bind,
    Replace,
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
        let provider_id = ProviderResourceId::new(self.provider_id.clone())
            .map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
        let generation = Generation::new(self.generation)
            .map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
        Ok(VmBinding {
            intent: intent.clone(),
            provider_id,
            generation,
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
struct LedgerState {
    head_id: Option<u64>,
    binding: Option<VmBinding>,
    terminal: bool,
}

pub struct DurableGitHubVmBindingStore {
    inner: BindingStore<GitHubDeploymentApi>,
}

impl DurableGitHubVmBindingStore {
    pub fn new(github_token: String, candidate_sha: String) -> Result<Self, BindingStoreError> {
        validate_candidate_sha(&candidate_sha)?;
        let backend = GitHubDeploymentApi::new(github_token)?;
        Ok(Self {
            inner: BindingStore {
                backend,
                candidate_sha,
            },
        })
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
                formatter.write_str("cleared ownership intent is terminal and cannot be rebound")
            }
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

    fn current_state(&self, intent: &OwnershipIntent) -> Result<LedgerState, BindingStoreError> {
        self.validate_intent(intent)?;
        let records = self.backend.list_records(&self.candidate_sha)?;
        reconstruct_ledger(records, &self.candidate_sha)
    }

    fn validate_binding(&self, binding: &VmBinding) -> Result<(), BindingStoreError> {
        self.validate_intent(&binding.intent)?;
        validate_provider_uuid(binding.provider_id.as_str())?;
        Ok(())
    }
}

impl<B: DeploymentBackend> VmBindingStore for BindingStore<B> {
    type Error = BindingStoreError;

    fn load(&self, intent: &OwnershipIntent) -> Result<Option<VmBinding>, Self::Error> {
        Ok(self.current_state(intent)?.binding)
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
        if before.binding.as_ref() != expected {
            return Err(BindingStoreError::CompareAndSwapConflict);
        }
        if before.terminal {
            return Err(BindingStoreError::TerminalIntentReuse);
        }

        let transition = validate_transition(expected, replacement.as_ref())?;
        let payload = GitHubDeploymentPayload {
            format_version: LEDGER_FORMAT_VERSION,
            project: OWNERSHIP_PROJECT.to_owned(),
            managed_by: OWNERSHIP_MANAGER.to_owned(),
            candidate_sha: self.candidate_sha.clone(),
            scope: LifecycleScope::Acceptance,
            intent_id: intent.id().to_owned(),
            predecessor_deployment_id: before.head_id,
            transition,
            expected: expected.map(BindingPayload::from_binding),
            replacement: replacement.as_ref().map(BindingPayload::from_binding),
        };
        let created = self.backend.append_record(NewDeploymentRecord {
            candidate_sha: self.candidate_sha.clone(),
            payload,
        })?;

        let after = self.current_state(intent)?;
        let terminal_expected = replacement.is_none();
        if after.head_id != Some(created.id)
            || after.binding != replacement
            || after.terminal != terminal_expected
        {
            return Err(BindingStoreError::WriteVerificationFailed);
        }
        Ok(())
    }
}

fn validate_transition(
    expected: Option<&VmBinding>,
    replacement: Option<&VmBinding>,
) -> Result<LedgerTransition, BindingStoreError> {
    match (expected, replacement) {
        (None, Some(replacement)) => {
            if replacement.generation != Generation::INITIAL {
                return Err(BindingStoreError::InvalidTransition);
            }
            Ok(LedgerTransition::Bind)
        }
        (Some(expected), Some(replacement)) => {
            let next = expected
                .generation
                .next()
                .map_err(|_| BindingStoreError::InvalidTransition)?;
            if replacement.intent != expected.intent
                || replacement.generation != next
                || replacement.provider_id == expected.provider_id
            {
                return Err(BindingStoreError::InvalidTransition);
            }
            Ok(LedgerTransition::Replace)
        }
        (Some(_), None) => Ok(LedgerTransition::Clear),
        (None, None) => Err(BindingStoreError::InvalidTransition),
    }
}

fn reconstruct_ledger(
    mut records: Vec<DeploymentRecord>,
    candidate_sha: &str,
) -> Result<LedgerState, BindingStoreError> {
    validate_candidate_sha(candidate_sha)?;
    records.sort_by_key(|record| record.id);
    let mut ids = BTreeSet::new();
    let intent = OwnershipIntent::new(
        LifecycleScope::Acceptance,
        format!("candidate:{candidate_sha}"),
    )
    .map_err(|_| BindingStoreError::InvalidOwnershipIntent)?;
    let mut state = LedgerState {
        head_id: None,
        binding: None,
        terminal: false,
    };

    for record in records {
        if !ids.insert(record.id) {
            return Err(BindingStoreError::ForkedLedger);
        }
        validate_record(&record, candidate_sha, &intent)?;
        if record.payload.predecessor_deployment_id != state.head_id {
            return Err(BindingStoreError::ForkedLedger);
        }
        let current_payload = state.binding.as_ref().map(BindingPayload::from_binding);
        if record.payload.expected != current_payload {
            return Err(BindingStoreError::ForkedLedger);
        }
        if state.terminal {
            return Err(BindingStoreError::TerminalIntentReuse);
        }

        match record.payload.transition {
            LedgerTransition::Bind => {
                if state.head_id.is_some() || state.binding.is_some() {
                    return Err(BindingStoreError::InvalidTransition);
                }
                let replacement = record
                    .payload
                    .replacement
                    .as_ref()
                    .ok_or(BindingStoreError::InvalidTransition)?
                    .to_binding(&intent)?;
                validate_transition(None, Some(&replacement))?;
                state.binding = Some(replacement);
            }
            LedgerTransition::Replace => {
                let current = state
                    .binding
                    .as_ref()
                    .ok_or(BindingStoreError::InvalidTransition)?;
                let replacement = record
                    .payload
                    .replacement
                    .as_ref()
                    .ok_or(BindingStoreError::InvalidTransition)?
                    .to_binding(&intent)?;
                validate_transition(Some(current), Some(&replacement))?;
                state.binding = Some(replacement);
            }
            LedgerTransition::Clear => {
                let current = state
                    .binding
                    .as_ref()
                    .ok_or(BindingStoreError::InvalidTransition)?;
                validate_transition(Some(current), None)?;
                if record.payload.replacement.is_some() {
                    return Err(BindingStoreError::InvalidTransition);
                }
                state.binding = None;
                state.terminal = true;
            }
        }
        state.head_id = Some(record.id);
    }
    Ok(state)
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
    if let Some(binding) = payload.expected.as_ref() {
        validate_provider_uuid(&binding.provider_id)?;
        Generation::new(binding.generation)
            .map_err(|_| BindingStoreError::InvalidLedgerRecord)?;
    }
    if let Some(binding) = payload.replacement.as_ref() {
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
        let client = Client::builder()
            .timeout(Duration::from_secs(20))
            .build()
            .map_err(|_| BindingStoreError::HttpTransport)?;
        Ok(Self { client, token })
    }

    fn deployments_url(&self) -> String {
        format!("{GITHUB_API_BASE}/repos/{CANONICAL_REPOSITORY}/deployments")
    }

    fn request(&self, method: reqwest::Method, url: &str) -> reqwest::blocking::RequestBuilder {
        self.client
            .request(method, url)
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
                .request(reqwest::Method::GET, &self.deployments_url())
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
        let body = json!({
            "ref": record.candidate_sha,
            "task": DEPLOYMENT_TASK,
            "auto_merge": false,
            "required_contexts": [],
            "payload": record.payload,
            "environment": DEPLOYMENT_ENVIRONMENT,
            "description": "mobile-proxy durable acceptance VM binding",
            "transient_environment": true,
            "production_environment": false
        });
        let response = self
            .request(reqwest::Method::POST, &self.deployments_url())
            .json(&body)
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

    #[test]
    fn durable_state_restores_exact_binding_after_restart() {
        let backend = MemoryBackend::default();
        let first = binding(ID1, 1);
        let mut writer = store(backend.clone());
        writer
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();
        drop(writer);

        let reader = store(backend);
        assert_eq!(reader.load(&intent()).unwrap(), Some(first));
    }

    #[test]
    fn stale_compare_and_swap_is_rejected_without_appending() {
        let backend = MemoryBackend::default();
        let first = binding(ID1, 1);
        let mut writer = store(backend.clone());
        writer
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();

        let stale = binding(ID2, 1);
        assert_eq!(
            writer.compare_and_swap(&intent(), Some(&stale), Some(binding(ID3, 2))),
            Err(BindingStoreError::CompareAndSwapConflict)
        );
        assert_eq!(backend.records.borrow().len(), 1);
    }

    #[test]
    fn replacement_requires_exact_next_generation_and_new_provider_id() {
        let backend = MemoryBackend::default();
        let first = binding(ID1, 1);
        let mut writer = store(backend.clone());
        writer
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();

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
    fn clear_is_terminal_and_cannot_restart_generation_one() {
        let backend = MemoryBackend::default();
        let first = binding(ID1, 1);
        let mut writer = store(backend.clone());
        writer
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();
        writer
            .compare_and_swap(&intent(), Some(&first), None)
            .unwrap();
        assert_eq!(writer.load(&intent()).unwrap(), None);
        drop(writer);

        let mut restarted = store(backend);
        assert_eq!(
            restarted.compare_and_swap(&intent(), None, Some(binding(ID2, 1))),
            Err(BindingStoreError::TerminalIntentReuse)
        );
    }

    #[test]
    fn forked_deployment_history_fails_closed() {
        let backend = MemoryBackend::default();
        let first = binding(ID1, 1);
        let mut writer = store(backend.clone());
        writer
            .compare_and_swap(&intent(), None, Some(first.clone()))
            .unwrap();

        let base = backend.records.borrow()[0].clone();
        for (id, provider_id) in [(2, ID2), (3, ID3)] {
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
                    predecessor_deployment_id: Some(base.id),
                    transition: LedgerTransition::Replace,
                    expected: Some(BindingPayload::from_binding(&first)),
                    replacement: Some(BindingPayload::from_binding(&binding(provider_id, 2))),
                },
            });
        }

        assert_eq!(
            store(backend).load(&intent()),
            Err(BindingStoreError::ForkedLedger)
        );
    }

    #[test]
    fn production_or_wrong_candidate_intent_is_rejected() {
        let backend = MemoryBackend::default();
        let store = store(backend);
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
        let invalid = VmBinding {
            intent: intent(),
            provider_id: ProviderResourceId::new("NOT-A-VULTR-UUID").unwrap(),
            generation: Generation::INITIAL,
        };
        assert_eq!(
            writer.compare_and_swap(&intent(), None, Some(invalid)),
            Err(BindingStoreError::InvalidProviderUuid)
        );
        assert!(backend.records.borrow().is_empty());
    }
}
