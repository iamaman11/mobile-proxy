use crate::vultr_lifecycle::{
    VultrAdapterError, VultrInstanceDto, VultrLifecycleAdapter, VultrMethod, VultrRequest,
    VultrVmSpec,
};
use proxy_core::{LifecycleScope, ObservedVm, PlannedCreate, VerifiedMutationTarget};
use reqwest::blocking::Client;
use serde::Deserialize;
use std::fmt;
use std::time::Duration;

const VULTR_API_BASE: &str = "https://api.vultr.com";
const VULTR_API_VERSION: &str = "v2";
const MAX_RESPONSE_BYTES: usize = 8 * 1024 * 1024;

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
            Self::Adapter(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for VultrClientError {}

trait VultrTransport {
    fn execute(&self, request: VultrRequest) -> Result<Vec<u8>, VultrClientError>;
}

struct AcceptanceClient<T> {
    transport: T,
}

impl<T: VultrTransport> AcceptanceClient<T> {
    fn list_instances(&self) -> Result<Vec<ObservedVm>, VultrClientError> {
        let body = self
            .transport
            .execute(VultrLifecycleAdapter::list_instances_request())?;
        VultrLifecycleAdapter::decode_instances(&body).map_err(VultrClientError::Adapter)
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
}

impl VultrTransport for ReqwestVultrTransport {
    fn execute(&self, request: VultrRequest) -> Result<Vec<u8>, VultrClientError> {
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
        let url = format!("{VULTR_API_BASE}{}", request.path);
        let mut builder = self
            .client
            .request(method, url)
            .bearer_auth(&self.api_token)
            .header("Accept", "application/json")
            .header("User-Agent", "mobile-proxy-operator-cli");
        if let Some(body) = request.body {
            builder = builder.json(&body);
        }
        let response = builder.send().map_err(|_| VultrClientError::Transport)?;
        if !response.status().is_success() {
            return Err(VultrClientError::HttpStatus(response.status().as_u16()));
        }
        let bytes = response.bytes().map_err(|_| VultrClientError::Transport)?;
        if bytes.len() > MAX_RESPONSE_BYTES {
            return Err(VultrClientError::ResponseTooLarge);
        }
        Ok(bytes.to_vec())
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

    struct FakeTransport {
        requests: RefCell<Vec<VultrRequest>>,
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
        fn execute(&self, request: VultrRequest) -> Result<Vec<u8>, VultrClientError> {
            self.requests.borrow_mut().push(request);
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

    fn created_response() -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "instance": {
                "id": ID1,
                "label": "mobile-proxy-acceptance",
                "tags": exact_tags(),
                "region": "waw",
                "plan": "vc2-1c-2gb",
                "os_id": 2284
            }
        }))
        .unwrap()
    }

    #[test]
    fn list_maps_vultr_dto_through_existing_typed_adapter() {
        let response = serde_json::to_vec(&serde_json::json!({
            "instances": [{
                "id": ID1,
                "label": "mobile-proxy-acceptance",
                "tags": exact_tags(),
                "region": "waw",
                "plan": "vc2-1c-2gb",
                "os_id": 2284
            }]
        }))
        .unwrap();
        let transport = FakeTransport::new(vec![response]);
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
        assert_eq!(requests[0], VultrLifecycleAdapter::list_instances_request());
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
            requests[0],
            VultrLifecycleAdapter::create_request(&plan, &spec())
        );
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
        assert_eq!(requests[0], VultrLifecycleAdapter::delete_request(&target));
    }
}
