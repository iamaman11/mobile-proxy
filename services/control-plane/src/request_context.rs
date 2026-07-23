use std::str::FromStr;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::{
    Json,
    extract::Request,
    http::{HeaderMap, HeaderValue, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use mobile_proxy_foundation::{
    ActorId, ApplicationId, ConsumerId, CorrelationId, Deadline, FoundationError,
    MAX_DEADLINE_WINDOW_SECS, RequestContext, RequestId,
};
use uuid::Uuid;

const REQUEST_ID_HEADER: &str = "x-request-id";
const CORRELATION_ID_HEADER: &str = "x-correlation-id";
const CONSUMER_ID_HEADER: &str = "x-consumer-id";
const APPLICATION_ID_HEADER: &str = "x-application-id";
const ACTOR_ID_HEADER: &str = "x-actor-id";
const DEADLINE_HEADER: &str = "x-deadline-unix-secs";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RequestContextError {
    Invalid,
    Expired,
}

impl IntoResponse for RequestContextError {
    fn into_response(self) -> Response {
        let (status, code) = match self {
            Self::Invalid => (StatusCode::BAD_REQUEST, "invalid_request_context"),
            Self::Expired => (StatusCode::REQUEST_TIMEOUT, "request_deadline_expired"),
        };
        (status, Json(serde_json::json!({ "error": code }))).into_response()
    }
}

pub async fn attach_request_context(mut request: Request, next: Next) -> Response {
    let context = match context_from_headers(request.headers()) {
        Ok(context) => context,
        Err(error) => return error.into_response(),
    };
    let request_id = context.request_id();
    let correlation_id = context.correlation_id();
    request.extensions_mut().insert(context);

    let mut response = next.run(request).await;
    response.headers_mut().insert(
        REQUEST_ID_HEADER,
        HeaderValue::from_str(&request_id.to_string()).expect("UUID is a valid header value"),
    );
    response.headers_mut().insert(
        CORRELATION_ID_HEADER,
        HeaderValue::from_str(&correlation_id.to_string()).expect("UUID is a valid header value"),
    );
    response
}

fn context_from_headers(headers: &HeaderMap) -> Result<RequestContext, RequestContextError> {
    let request_id = parse_header::<RequestId>(headers, REQUEST_ID_HEADER)?
        .unwrap_or_else(|| RequestId::from_uuid(Uuid::new_v4()));
    let correlation_id = parse_header::<CorrelationId>(headers, CORRELATION_ID_HEADER)?
        .unwrap_or_else(|| CorrelationId::from_uuid(request_id.as_uuid()));
    let consumer_id = parse_header::<ConsumerId>(headers, CONSUMER_ID_HEADER)?;
    let application_id = parse_header::<ApplicationId>(headers, APPLICATION_ID_HEADER)?;
    let actor_id = parse_header::<ActorId>(headers, ACTOR_ID_HEADER)?;
    let deadline = parse_deadline(headers)?;

    Ok(RequestContext::new(
        request_id,
        correlation_id,
        consumer_id,
        application_id,
        actor_id,
        deadline,
    ))
}

fn parse_header<T>(
    headers: &HeaderMap,
    name: &'static str,
) -> Result<Option<T>, RequestContextError>
where
    T: FromStr<Err = FoundationError>,
{
    let Some(value) = headers.get(name) else {
        return Ok(None);
    };
    let raw = value.to_str().map_err(|_| RequestContextError::Invalid)?;
    raw.parse()
        .map(Some)
        .map_err(|_| RequestContextError::Invalid)
}

fn parse_deadline(headers: &HeaderMap) -> Result<Option<Deadline>, RequestContextError> {
    let Some(value) = headers.get(DEADLINE_HEADER) else {
        return Ok(None);
    };
    let raw = value.to_str().map_err(|_| RequestContextError::Invalid)?;
    let unix_secs = raw
        .parse::<u64>()
        .map_err(|_| RequestContextError::Invalid)?;
    let deadline = Deadline::from_unix_secs(unix_secs);
    let now = now_unix_secs();
    if deadline.is_expired(now) {
        return Err(RequestContextError::Expired);
    }
    if deadline.remaining_secs(now) > u64::from(MAX_DEADLINE_WINDOW_SECS) {
        return Err(RequestContextError::Invalid);
    }
    Ok(Some(deadline))
}

fn now_unix_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use axum::http::{HeaderMap, HeaderValue};
    use mobile_proxy_foundation::{ApplicationId, Deadline};

    use super::{CORRELATION_ID_HEADER, DEADLINE_HEADER, REQUEST_ID_HEADER, context_from_headers};

    #[test]
    fn supplied_request_lineage_round_trips() {
        let mut headers = HeaderMap::new();
        headers.insert(
            REQUEST_ID_HEADER,
            HeaderValue::from_static("98da1dbc-7de7-4bd2-8a5c-e24af5131f38"),
        );
        headers.insert(
            CORRELATION_ID_HEADER,
            HeaderValue::from_static("4cd306ef-716e-4f76-aef6-679b93bb7770"),
        );
        headers.insert("x-application-id", HeaderValue::from_static("operator-cli"));
        let context = context_from_headers(&headers).unwrap();
        assert_eq!(
            context.request_id().to_string(),
            "98da1dbc-7de7-4bd2-8a5c-e24af5131f38"
        );
        assert_eq!(
            context.correlation_id().to_string(),
            "4cd306ef-716e-4f76-aef6-679b93bb7770"
        );
        assert_eq!(
            context.application_id().map(ApplicationId::as_str),
            Some("operator-cli")
        );
    }

    #[test]
    fn absent_correlation_uses_request_identity() {
        let mut headers = HeaderMap::new();
        headers.insert(
            REQUEST_ID_HEADER,
            HeaderValue::from_static("98da1dbc-7de7-4bd2-8a5c-e24af5131f38"),
        );
        let context = context_from_headers(&headers).unwrap();
        assert_eq!(
            context.request_id().as_uuid(),
            context.correlation_id().as_uuid()
        );
    }

    #[test]
    fn malformed_or_unbounded_headers_fail_closed() {
        let mut malformed = HeaderMap::new();
        malformed.insert(
            REQUEST_ID_HEADER,
            HeaderValue::from_static("credential=secret"),
        );
        assert!(context_from_headers(&malformed).is_err());

        let mut distant = HeaderMap::new();
        let distant_deadline = super::now_unix_secs() + 86_401;
        distant.insert(
            DEADLINE_HEADER,
            HeaderValue::from_str(&distant_deadline.to_string()).unwrap(),
        );
        assert!(context_from_headers(&distant).is_err());
    }

    #[test]
    fn deadline_is_retained_as_an_absolute_value() {
        let mut headers = HeaderMap::new();
        let deadline = super::now_unix_secs() + 30;
        headers.insert(
            DEADLINE_HEADER,
            HeaderValue::from_str(&deadline.to_string()).unwrap(),
        );
        let context = context_from_headers(&headers).unwrap();
        assert_eq!(context.deadline().map(Deadline::unix_secs), Some(deadline));
    }
}
