use crate::vultr_lifecycle::{
    VultrAdapterError, VultrInstanceDto, VultrLifecycleAdapter, VultrMethod, VultrRequest,
    VultrVmSpec,
};
use proxy_core::{LifecycleScope, ObservedVm, PlannedCreate, VerifiedMutationTarget};
use reqwest::blocking::{Client, Response};
use serde::Deserialize;
use std::collections::BTreeSet;
use std::fmt;
use std::io::Read;
use std::time::Duration;

const VULTR_API_BASE: &str = "https://api.vultr.com";
const VULTR_API_VERSION: &str = "v2";
const MAX_RESPONSE_BYTES: usize = 8 * 1024 * 1024;
const INSTANCE_PAGE_SIZE: u32 = 500;
const MAX_INSTANCE_PAGES: usize = 20;
const MAX_CURSOR_BYTES: usize = 1024;

pub struct VultrAcceptanceClient {
    inner: AcceptanceClient<ReqwestVultrTransport>,
}

impl VultrAcceptanceClient {
    pub fn new(api_token: String) -> Result<Self, VultrClientError> {
        Ok(Self {
            inner: AcceptanceClient {
                transport: ReqwestVultrTransport::new(api_token)?,
            },
        })
    }

    pub fn list_instances(&self) -> Result<Vec<ObservedVm>, VultrClientError> {
        self.inner.list_instances()
    }

    pub fn create_instance(
        &self,
        plan: &PlannedCreate,
        spec: &VultrVmSpec,
    ) -> Result<ObservedVm, VultrClientError> {
        self.inner.create_instance(plan, spec)
    }

    pub fn delete_instance(
        &self,
        target: &VerifiedMutationTarget,
    ) -> Result<(), VultrClientError> {
        self.inner.delete_instance(target)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VultrClientError {
    AcceptanceScopeRequired,
    Transport,
    HttpStatus(u16),
    ResponseTooLarge,
    InvalidResponse,
    InvalidPagination,
    PaginationLimitExceeded,
    Adapter(VultrAdapterError),
}

impl fmt::Display for VultrClientError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::AcceptanceScopeRequired => {
                formatter.write_str("live Vultr client is restricted to acceptance scope")
            }
            Self::Transport => formatter.write_str("Vultr HTTP transport failed"),
            Self::HttpStatus(status) => write!(formatter, "Vultr HTTP status {status}"),
            Self::ResponseTooLarge => formatter.write_str("Vultr response exceeded bounded size"),
            Self::InvalidResponse => formatter.write_str("Vultr response shape is invalid"),
            Self::InvalidPagination => formatter.write_str("Vultr pagination metadata is invalid"),
            Self::PaginationLimitExceeded => {
                formatter.write_str("Vultr instance listing exceeded bounded page count")
            }
            Self::Adapter(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for VultrClientError {}

trait VultrTransport {
    fn execute_with_query(
        &self,
        request: VultrRequest,
        query: &[(String, String)],
    ) -> Result<Vec<u8>, VultrClientError>;

    fn execute(&self, request: VultrRequest) -> Result<Vec<u8>, VultrClientError> {
        self.execute_with_query(request, &[])
    }
}

struct AcceptanceClient<T> {
    transport: T,
}

impl<T: VultrTransport> AcceptanceClient<T> {
    fn list_instances(&self) -> Result<Vec<ObservedVm>, VultrClientError> {
        let mut observed = Vec::new();
        let mut cursor: Option<String> = None;
        let mut seen_cursors = BTreeSet::new();

        for _ in 0..MAX_INSTANCE_PAGES {
            let mut query = vec![("per_page".to_owned(), INSTANCE_PAGE_SIZE.to_string())];
            if let Some(value) = cursor.as_ref() {
                query.push(("cursor".to_owned(), value.clone()));
            }

            let body = self.transport.execute_with_query(
                VultrLifecycleAdapter::list_instances_request(),
                &query,
            )?;
            let page: InstancesPage =
                serde_json::from_slice(&body).map_err(|_| VultrClientError::InvalidResponse)?;
            let count = page.instances.len();
            observed.extend(
                page.instances
                    .into_iter()
                    .map(VultrLifecycleAdapter::decode_instance)
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(VultrClientError::Adapter)?,
            );

            let next = page
                .meta
                .and_then(|meta| meta.links)
                .map(|links| links.next)
                .unwrap_or_default();
            if next.is_empty() {
                if count >= INSTANCE_PAGE_SIZE as usize && page.meta_was_missing {
                    return Err(VultrClientError::InvalidPagination);
                }
                return Ok(observed);
            }
            if next.len() > MAX_CURSOR_BYTES || !seen_cursors.insert(next.clone()) {
                return Err(VultrClientError::InvalidPagination);
            }
            cursor = Some(next);
        }

        Err(VultrClientError::PaginationLimitExceeded)
    }

    fn create_instance(
        &self,
        plan: &PlannedCreate,
        spec: &VultrVmSpec,
    ) -> Result<ObservedVm, VultrClientError> {
        require_acceptance(plan.intent().scope())?;
        let body = self
            .transport
            .execute(VultrLifecycleAdapter::create_request(plan, spec))?;
        let envelope: CreatedInstanceEnvelope =
            serde_json::from_slice(&body).map_err(|_| VultrClientError::InvalidResponse)?;
        VultrLifecycleAdapter::decode_instance(envelope.instance).map_err(VultrClientError::Adapter)
    }

    fn delete_instance(
        &self,
        target: &VerifiedMutationTarget,
    ) -> Result<(), VultrClientError> {
        require_acceptance(target.intent().scope())?;
        self.transport
            .execute(VultrLifecycleAdapter::delete_request(target))?;
        Ok(())
    }
}

fn require_acceptance(scope: LifecycleScope) -> Result<(), VultrClientError> {
    if scope != LifecycleScope::Acceptance {
        return Err(VultrClientError::AcceptanceScopeRequired);
    }
    Ok(())
}

#[derive(Deserialize)]
struct CreatedInstanceEnvelope {
    instance: VultrInstanceDto,
}

#[derive(Deserialize)]
struct InstancesPageWire {
    instances: Vec<VultrInstanceDto>,
    #[serde(default)]
    meta: Option<PageMeta>,
}

struct InstancesPage {
    instances: Vec<VultrInstanceDto>,
    meta: Option<PageMeta>,
    meta_was_missing: bool,
}

impl<'de> Deserialize<'de> for InstancesPage {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let wire = InstancesPageWire::deserialize(deserializer)?;
        let meta_was_missing = wire.meta.is_none();
        Ok(Self {
            instances: wire.instances,
            meta: wire.meta,
            meta_was_missing,
        })
    }
}

#[derive(Deserialize)]
struct PageMeta {
    #[serde(default)]
    links: Option<PageLinks>,
}

#[derive(Deserialize)]
struct PageLinks {
    #[serde(default)]
    next: String,
}

struct ReqwestVultrTransport {
    client: Client,
    api_token: String,
}

impl ReqwestVultrTransport {
    fn new(api_token: String) -> Result<Self, VultrClientError> {
        if api_token.is_empty() {
            return Err(VultrClientError::Transport);
        }
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|_| VultrClientError::Transport)?;
        Ok(Self { client, api_token })
    }

    fn read_bounded(response: Response) -> Result<Vec<u8>, VultrClientError> {
        if response
            .content_length()
            .is_some_and(|length| length > MAX_RESPONSE_BYTES as u64)
        {
            return Err(VultrClientError::ResponseTooLarge);
        }
        let mut reader = response.take((MAX_RESPONSE_BYTES + 1) as u64);
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .map_err(|_| VultrClientError::Transport)?;
        if bytes.len() > MAX_RESPONSE_BYTES {
            return Err(VultrClientError::ResponseTooLarge);
        }
        Ok(bytes)
    }
}

impl VultrTransport for ReqwestVultrTransport {
    fn execute_with_query(
        &self,
        request: VultrRequest,
        query: &[(String, String)],
    ) -> Result<Vec<u8>, VultrClientError> {
        if !request.path.starts_with(&format!("/{VULTR_API_VERSION}/"))
            || request.path.contains("..")
            || request.path.contains('?')
            || request.path.contains('#')
        {
            return Err(VultrClientError::Transport);
        }
        let method = match request.method {
            VultrMethod::Get => reqwest::Method::GET,
            VultrMethod::Post => reqwest::Method::POST,
            VultrMethod::Patch => reqwest::Method::PATCH,
            VultrMethod::Delete => reqwest::Method::DELETE,
        };
        if method != reqwest::Method::GET && !query.is_empty() {
            return Err(VultrClientError::Transport);
        }
        if query.iter().any(|(key, value)| {
            !matches!(key.as_str(), "per_page" | "cursor")
                || key.is_empty()
                || value.is_empty()
                || value.len() > MAX_CURSOR_BYTES
        }) {
            return Err(VultrClientError::Transport);
        }

        let url = format!("{VULTR_API_BASE}{}", request.path);
        let mut builder = self
            .client
            .request(method, url)
            .bearer_auth(&self.api_token)
            .header("Accept", "application/json")
            .header("User-Agent", "mobile-proxy-operator-cli")
            .query(query);
        if let Some(body) = request.body {
            builder = builder.json(&body);
        }
        let response = builder.send().map_err(|_| VultrClientError::Transport)?;
        if !response.status().is_success() {
            return Err(VultrClientError::HttpStatus(response.status().as_u16()));
        }
        Self::read_bounded(response)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use proxy_core::{
        DesiredVm, Generation, MutationKind, OwnershipIntent, OwnershipMetadata,
        OwnershipObservation, ProviderResourceId, ReconcilePlan, VmBinding, authorize_mutation,
        plan_present,
    };
    use std::cell::RefCell;

    const ID1: &str = "11111111-1111-4111-8111-111111111111";
    const ID2: &str = "22222222-2222-4222-8222-222222222222";

    #[derive(Clone, Debug, Eq, PartialEq)]
    struct RecordedRequest {
        request: VultrRequest,
        query: Vec<(String, String)>,
    }

    struct FakeTransport {
        requests: RefCell<Vec<RecordedRequest>>,
        responses: RefCell<Vec<Vec<u8>>>,
    }

    impl FakeTransport {
        fn new(responses: Vec<Vec<u8>>) -> Self {
            Self {
                requests: RefCell::new(Vec::new()),
                responses: RefCell::new(responses.into_iter().rev().collect()),
            }
        }
    }

    impl VultrTransport for FakeTransport {
        fn execute_with_query(
            &self,
            request: VultrRequest,
            query: &[(String, String)],
        ) -> Result<Vec<u8>, VultrClientError> {
            self.requests.borrow_mut().push(RecordedRequest {
                request,
                query: query.to_vec(),
            });
            self.responses
                .borrow_mut()
                .pop()
                .ok_or(VultrClientError::Transport)
        }
    }

    fn intent(scope: LifecycleScope) -> OwnershipIntent {
        OwnershipIntent::new(
            scope,
            "candidate:0123456789abcdef0123456789abcdef01234567",
        )
        .unwrap()
    }

    fn spec() -> VultrVmSpec {
        VultrVmSpec {
            region: "waw".to_owned(),
            plan: "vc2-1c-2gb".to_owned(),
            os_id: 2284,
            label: "mobile-proxy-acceptance".to_owned(),
        }
    }

    fn planned_create(scope: LifecycleScope) -> PlannedCreate {
        let desired = DesiredVm {
            intent: intent(scope),
            display_name: spec().label.clone(),
            spec_fingerprint: spec().fingerprint(),
        };
        let ReconcilePlan::Create(plan) = plan_present(None, &[], &desired, None).unwrap() else {
            panic!("expected create plan");
        };
        plan
    }

    fn exact_tags() -> Vec<String> {
        crate::vultr_lifecycle::encode_ownership(&OwnershipMetadata::exact(
            &intent(LifecycleScope::Acceptance),
            Generation::INITIAL,
        ))
    }

    fn instance_json(id: &str) -> serde_json::Value {
        serde_json::json!({
            "id": id,
            "label": "mobile-proxy-acceptance",
            "tags": exact_tags(),
            "region": "waw",
            "plan": "vc2-1c-2gb",
            "os_id": 2284
        })
    }

    fn created_response() -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "instance": instance_json(ID1)
        }))
        .unwrap()
    }

    fn list_page(instances: Vec<serde_json::Value>, next: &str) -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "instances": instances,
            "meta": { "links": { "next": next } }
        }))
        .unwrap()
    }

    #[test]
    fn list_maps_vultr_dto_through_existing_typed_adapter() {
        let transport = FakeTransport::new(vec![list_page(vec![instance_json(ID1)], "")]);
        let client = AcceptanceClient { transport };

        let observed = client.list_instances().unwrap();
        assert_eq!(observed.len(), 1);
        assert_eq!(observed[0].provider_id.as_str(), ID1);
        assert!(matches!(
            observed[0].ownership,
            OwnershipObservation::Exact(_)
        ));
        let requests = client.transport.requests.borrow();
        assert_eq!(requests.len(), 1);
        assert_eq!(requests[0].request, VultrLifecycleAdapter::list_instances_request());
        assert_eq!(
            requests[0].query,
            vec![("per_page".to_owned(), INSTANCE_PAGE_SIZE.to_string())]
        );
    }

    #[test]
    fn list_follows_every_cursor_before_returning_provider_state() {
        let transport = FakeTransport::new(vec![
            list_page(vec![instance_json(ID1)], "cursor-two"),
            list_page(vec![instance_json(ID2)], ""),
        ]);
        let client = AcceptanceClient { transport };

        let observed = client.list_instances().unwrap();
        assert_eq!(observed.len(), 2);
        let requests = client.transport.requests.borrow();
        assert_eq!(requests.len(), 2);
        assert_eq!(
            requests[1].query,
            vec![
                ("per_page".to_owned(), INSTANCE_PAGE_SIZE.to_string()),
                ("cursor".to_owned(), "cursor-two".to_owned()),
            ]
        );
    }

    #[test]
    fn repeated_cursor_fails_closed() {
        let transport = FakeTransport::new(vec![
            list_page(vec![], "same-cursor"),
            list_page(vec![], "same-cursor"),
        ]);
        let client = AcceptanceClient { transport };

        assert_eq!(client.list_instances(), Err(VultrClientError::InvalidPagination));
    }

    #[test]
    fn create_uses_planned_create_and_exact_adapter_tags() {
        let transport = FakeTransport::new(vec![created_response()]);
        let client = AcceptanceClient { transport };
        let plan = planned_create(LifecycleScope::Acceptance);

        let observed = client.create_instance(&plan, &spec()).unwrap();
        assert_eq!(observed.provider_id.as_str(), ID1);
        let requests = client.transport.requests.borrow();
        assert_eq!(requests.len(), 1);
        assert_eq!(
            requests[0].request,
            VultrLifecycleAdapter::create_request(&plan, &spec())
        );
        assert!(requests[0].query.is_empty());
    }

    #[test]
    fn production_create_is_rejected_before_http_transport() {
        let transport = FakeTransport::new(vec![]);
        let client = AcceptanceClient { transport };
        let plan = planned_create(LifecycleScope::Production);

        assert_eq!(
            client.create_instance(&plan, &spec()),
            Err(VultrClientError::AcceptanceScopeRequired)
        );
        assert!(client.transport.requests.borrow().is_empty());
    }

    #[test]
    fn delete_accepts_only_provider_neutral_verified_target() {
        let generation = Generation::new(4).unwrap();
        let binding = VmBinding {
            intent: intent(LifecycleScope::Acceptance),
            provider_id: ProviderResourceId::new(ID1).unwrap(),
            generation,
        };
        let observed = ObservedVm {
            provider_id: ProviderResourceId::new(ID1).unwrap(),
            display_name: "mobile-proxy-acceptance".to_owned(),
            ownership: OwnershipObservation::Exact(OwnershipMetadata::exact(
                &binding.intent,
                generation,
            )),
            spec_fingerprint: spec().fingerprint(),
        };
        let target = authorize_mutation(&binding, &[observed], generation, MutationKind::Delete)
            .unwrap();
        let transport = FakeTransport::new(vec![vec![]]);
        let client = AcceptanceClient { transport };

        client.delete_instance(&target).unwrap();
        let requests = client.transport.requests.borrow();
        assert_eq!(requests.len(), 1);
        assert_eq!(requests[0].request, VultrLifecycleAdapter::delete_request(&target));
        assert!(requests[0].query.is_empty());
    }
}
